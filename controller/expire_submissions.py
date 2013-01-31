import datetime
import json
from django.conf import settings
from django.utils import timezone
from create_grader import create_grader
import grader_util
import util
import logging
from models import GraderStatus, SubmissionState, Submission, Grader, Rubric, RubricItem
from staff_grading import staff_grading_util
from xqueue_interface import handle_submission
from ml_grading import ml_grading_util
from django.db import transaction

from statsd import statsd

log = logging.getLogger(__name__)

error_template = u"""

<section>
    <div class="shortform">
        <div class="result-errors">
          There was an error with your submission.  Please contact the course staff.
        </div>
    </div>
    <div class="longform">
        <div class="result-errors">
          {errors}
        </div>
    </div>
</section>

"""

def reset_ml_subs_to_in():
    """
    Reset submissions marked ML to instructor if there are not enough instructor submissions to grade
    This happens if the instructor skips too many submissions
    """
    counter=0
    unique_locations=[x['location'] for x in list(Submission.objects.values('location').distinct())]
    for location in unique_locations:
        subs_graded, subs_pending = staff_grading_util.count_submissions_graded_and_pending_instructor(location)
        subs_pending_total= Submission.objects.filter(
            location=location,
            state=SubmissionState.waiting_to_be_graded,
            preferred_grader_type="ML"
        ).order_by('-date_created')[:settings.MIN_TO_USE_ML]
        if ((subs_graded+subs_pending) < settings.MIN_TO_USE_ML and subs_pending_total.count() > subs_pending):
            for sub in subs_pending_total:
                if sub.next_grader_type=="ML" and sub.get_unsuccessful_graders().count()==0:
                    staff_grading_util.set_ml_grading_item_back_to_instructor(sub)
                    counter+=1
                if (counter+subs_graded + subs_pending)> settings.MIN_TO_USE_ML:
                    break
    if counter>0:
        statsd.increment("open_ended_assessment.grading_controller.expire_submissions.reset_ml_subs_to_in",
            tags=["counter:{0}".format(counter)])
        log.debug("Reset {0} submission from ML to IN".format(counter))

def reset_in_subs_to_ml(subs):
    count=0
    in_subs=Submission.objects.filter(
        state=SubmissionState.waiting_to_be_graded,
        next_grader_type="IN",
        preferred_grader_type="ML"
    )

    for sub in in_subs:
        #If an instructor checks out a submission after ML grading has started,
        # this resets it to ML if the instructor times out
        success= ml_grading_util.check_for_all_model_and_rubric_success(sub.location)
        if (sub.next_grader_type=="IN" and success):
            sub.next_grader_type="ML"
            sub.save()
            count+=1

    if count>0:
        statsd.increment("open_ended_assessment.grading_controller.expire_submissions.reset_in_subs_to_ml",
            tags=["counter:{0}".format(count)])
        log.debug("Reset {0} instructor subs to ML".format(count))

    return True

def reset_subs_in_basic_check(subs):
    #Reset submissions that are stuck in basic check state
    subs_stuck_in_basic_check=subs.filter(
        next_grader_type="BC",
        state__in=[SubmissionState.waiting_to_be_graded, SubmissionState.being_graded]
    )

    count=0
    for sub in subs_stuck_in_basic_check:
        handle_submission(sub)
        count+=1

    if count>0:
        statsd.increment("open_ended_assessment.grading_controller.expire_submissions.reset_subs_in_basic_check",
            tags=["counter:{0}".format(count)])
        log.debug("Reset {0} basic check subs properly.".format(count))
    return True

def reset_failed_subs_in_basic_check(subs):
    #Reset submissions that are stuck in basic check state
    subs_failed_basic_check=subs.filter(
        grader__grader_type="BC",
        grader__status_code= GraderStatus.failure,
        state=SubmissionState.waiting_to_be_graded,
    ).exclude(grader__status_code=GraderStatus.success)

    count=0
    for sub in subs_failed_basic_check:
        handle_submission(sub)
        count+=1

    if count>0:
        statsd.increment("open_ended_assessment.grading_controller.expire_submissions.reset_subs_failed_basic_check",
            tags=["counter:{0}".format(count)])
        log.debug("Reset {0} basic check failed subs properly.".format(count))
    return True

def reset_timed_out_submissions(subs):
    """
    Check if submissions have timed out, and reset them to waiting to grade state if they have
    Input:
        subs - A QuerySet of submissions
    Output:
        status code indicating success
    """
    now = timezone.now()
    min_time = datetime.timedelta(seconds=settings.RESET_SUBMISSIONS_AFTER)
    timed_out_subs=subs.filter(date_modified__lt=now-min_time)
    timed_out_sub_count=timed_out_subs.count()
    count = 0

    for i in xrange(0, timed_out_sub_count):
        sub = subs[i]
        if sub.state == SubmissionState.being_graded:
            sub.state = SubmissionState.waiting_to_be_graded
            sub.save()
            count += 1

    if count>0:
        statsd.increment("open_ended_assessment.grading_controller.expire_submissions.reset_timed_out_submissions",
            tags=["counter:{0}".format(count)])
        log.debug("Reset {0} submissions that had timed out in their current grader.".format(count))

    return True


def get_submissions_that_have_expired(subs):
    """
    Check if submissions have expired, and return them if they have.
    Input:
        subs - A queryset of submissions
    """
    now = timezone.now()
    min_time = datetime.timedelta(seconds=settings.EXPIRE_SUBMISSIONS_AFTER)
    expired_subs=subs.filter(date_modified__lt=now-min_time, posted_results_back_to_queue=False, state=SubmissionState.waiting_to_be_graded)

    return list(expired_subs)

def finalize_expired_submissions(timed_out_list):

    for sub in timed_out_list:
        finalize_expired_submission(sub)

    log.debug("Reset {0} submissions that had timed out in their current grader.".format(len(timed_out_list)))

    return True

def finalize_expired_submission(sub):
    """
    Expire submissions by posting back to LMS with error message.
    Input:
        timed_out_list from check_if_expired method
    Output:
        Success code.
    """

    grader_dict = {
        'score': 0,
        'feedback': error_template.format(errors="Error scoring submission."),
        'status': GraderStatus.failure,
        'grader_id': "0",
        'grader_type': sub.next_grader_type,
        'confidence': 1,
        'submission_id' : sub.id,
        }

    sub.state = SubmissionState.finished
    sub.save()

    grade = create_grader(grader_dict,sub)

    statsd.increment("open_ended_assessment.grading_controller.expire_submissions.finalize_expired_submission",
        tags=[
            "course:{0}".format(sub.course_id),
            "location:{0}".format(sub.location),
            'grader_type:{0}'.format(sub.next_grader_type)
              ])

    return True

def check_if_grading_finished_for_duplicates():
    duplicate_submissions = Submission.objects.filter(
        preferred_grader_type = "PE",
        is_duplicate= True,
        posted_results_back_to_queue=False,
    )
    counter=0
    for sub in duplicate_submissions:
        original_sub=Submission.objects.get(id=sub.duplicate_submission_id)
        if original_sub.state == SubmissionState.finished:
            finalize_grade_for_duplicate_peer_grader_submissions(sub, original_sub)
            counter+=1
            log.debug("Finalized one duplicate submission: Original: {0} Duplicate: {1}".format(original_sub,sub))

    statsd.increment("open_ended_assessment.grading_controller.expire_submissions.check_if_duplicate_grading_finished",
        tags=[
            "counter:{0}".format(counter),
        ])
    log.info("Finalized {0} duplicate submissions".format(counter))
    return True

def finalize_grade_for_duplicate_peer_grader_submissions(sub, original_sub):
    transaction.commit_unless_managed()
    original_grader_set = original_sub.grader_set.all()

    #Need to trickle through all layers to copy the info
    for grade in original_grader_set:
        rubric_set = list(grade.rubric_set.all())
        log.debug(grade.id)
        grade.pk = None
        grade.id = None
        grade.submission = sub
        grade.save()
        transaction.commit_unless_managed()
        for rubric in rubric_set:
            rubricitem_set = list(rubric.rubricitem_set.all())
            rubric.pk = None
            rubric.id = None
            rubric.grade = grade
            rubric.save()
            transaction.commit_unless_managed()
            for rubric_item in rubricitem_set:
                rubricoption_set = list(rubric_item.rubricoption_set.all())
                rubric_item.pk = None
                rubric_item.id = None
                rubric_item.rubric = rubric
                rubric_item.save()
                transaction.commit_unless_managed()
                for rubric_option in rubricoption_set:
                    rubric_option.pk = None
                    rubric_option.id = None
                    rubric_option.rubric_item = rubric_item
                    rubric_option.save()
                    transaction.commit_unless_managed()

    sub.state=SubmissionState.finished
    sub.previous_grader_type="PE"
    sub.save()

    return True