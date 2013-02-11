from django.conf import settings
from controller.create_grader import create_grader
from controller.models import Submission
import logging
from controller.models import SubmissionState, GraderStatus
from metrics import metrics_util
from metrics.timing_functions import initialize_timing
from controller import util
from ml_grading import ml_grading_util

log = logging.getLogger(__name__)

def generate_ml_error_message(ml_error_info):
    """
    Generates a message to send to the staff grading service from a dictionary returned by ml_grading_util.get_ml_errors
    Input:
        Dictionary with keys 'kappa', 'mean_absolute_error', 'date_created', 'number_of_essays'
    Output:
        String to send to staff grading service
    """

    ml_message_template="""
    Latest model created on {date_created}.  Contains {number_of_essays} essays.
    Mean absolute error is {mean_absolute_error} and kappa is {kappa}.
    """

    ml_message=ml_message_template.format(
        date_created=ml_error_info['date_created'],
        number_of_essays=ml_error_info['number_of_essays'],
        mean_absolute_error=ml_error_info['mean_absolute_error'],
        kappa=ml_error_info['kappa'],
    )

    return ml_message

def submissions_pending_for_location(location):
    """
    Get submissions that are graded by instructor
    """
    subs_graded = Submission.objects.filter(location=location,
        state=SubmissionState.waiting_to_be_graded,
    )

    return subs_graded


def finished_submissions_graded_by_instructor(location):
    """
    Get submissions that are graded by instructor
    """
    subs_graded = Submission.objects.filter(location=location,
        previous_grader_type="IN",
        state=SubmissionState.finished,
    )

    return subs_graded

def submission_text_graded_by_instructor(location):
    finished_subs=finished_submissions_graded_by_instructor(location)
    sub_text=finished_subs.values('student_response').distinct()
    return [s['student_response'] for s in sub_text]

def submissions_pending_instructor(location, state_in=[SubmissionState.being_graded, SubmissionState.waiting_to_be_graded]):
    """
    Get submissions that are pending instructor grading.
    """
    if len(state_in)==1:
        state_in = state_in[0]
        subs_pending = Submission.objects.filter(location=location,
            next_grader_type="IN",
            state=state_in,
            is_duplicate=False,
            is_plagiarized=False
        )
    else:
        subs_pending = Submission.objects.filter(location=location,
            next_grader_type="IN",
            state__in=state_in,
            is_duplicate=False,
            is_plagiarized=False
        )

    return subs_pending


def count_submissions_graded_and_pending_instructor(location):
    """
    Return length of submissions pending instructor grading and graded.
    """
    return finished_submissions_graded_by_instructor(location).count(), submissions_pending_instructor(location).count()

def get_single_instructor_grading_item_for_location_with_options(location,check_for_ml=True,types_to_check_for=None,
                                                                 submission_state_to_check_for=SubmissionState.waiting_to_be_graded):
    """
    Returns a single instructor grading item for a given location
    Input:
        Problem location, boolean check_for_ML, which dictates whether or not problems should be returned
        to the instructor if there is already an ML model trained for this location or not.  If True, then
        it does not return submissions for which an ML model has already been trained.
    Output:
        Boolean success/fail, and then either error message or submission id of a valid submission.
    """

    if not types_to_check_for:
        types_to_check_for="IN"

    log.debug("Looking for  location {0}, state {1}, next_grader_type {2}".format(location,
        submission_state_to_check_for, types_to_check_for))

    subs_graded = finished_submissions_graded_by_instructor(location).count()
    subs_pending = submissions_pending_instructor(location, state_in=[SubmissionState.being_graded]).count()
    success= ml_grading_util.check_for_all_model_and_rubric_success(location)

    if ((subs_graded + subs_pending) < settings.MIN_TO_USE_ML or not success) or not check_for_ml:
        to_be_graded = Submission.objects.filter(
            location=location,
            state=submission_state_to_check_for,
            next_grader_type=types_to_check_for,
        )

        #Order by confidence if we are looking for finished ML submissions
        finished_submission_text=submission_text_graded_by_instructor(location)
        if types_to_check_for == "ML" and submission_state_to_check_for == SubmissionState.finished:
            to_be_graded = to_be_graded.filter(grader__status_code=GraderStatus.success).order_by('grader__confidence')

        to_be_graded_count=to_be_graded.count()
        log.debug("Looking for  location {0} and got count {1}".format(location,to_be_graded_count))

        for i in xrange(0,to_be_graded_count):
            #In some cases, this causes a model query error without the try/except block due to the checked out state
            try:
                to_be_graded_obj = to_be_graded[i]
            except:
                return False, 0
            if to_be_graded_obj is not None and to_be_graded_obj.student_response not in finished_submission_text:
                to_be_graded_obj.state = SubmissionState.being_graded
                to_be_graded_obj.next_grader_type="IN"
                to_be_graded_obj.save()
                found = True
                sub_id = to_be_graded_obj.id

                #Insert timing initialization code
                initialize_timing(sub_id)

                return found, sub_id

        #If nothing is found, return false
    return False, 0

def get_single_instructor_grading_item_for_location(location):
    found = False
    sub_id = 0
    #Looks through first all submissions that are marked for instructor grading and are pending, then looks
    #through submissions that are marked for instructor or ML grading and are pending, then finally
    #looks through submisisons that have been marked finished and have been graded already by ML.
    success, sub_id = get_single_instructor_grading_item_for_location_with_options(location,check_for_ml=True)
    log.debug("Checked for ml.")
    if success:
        return success, sub_id

    success, sub_id = get_single_instructor_grading_item_for_location_with_options(location,check_for_ml=False,
        types_to_check_for="ML", submission_state_to_check_for=SubmissionState.finished)
    if success:
        return success, sub_id

    return found, sub_id

def get_single_instructor_grading_item(course_id):
    """
    Gets instructor grading for a given course id.
    Returns one submission id corresponding to the course.
    Input:
        course_id - Id of a course.
    Returns:
        found - Boolean indicating whether or not something to grade was found
        sub_id - If found, the id of a submission to grade
    """
    found = False
    sub_id = 0
    locations_for_course = [x['location'] for x in
                            list(Submission.objects.filter(course_id=course_id).values('location').distinct())]
    log.debug("locations: {0} for course {1}".format(locations_for_course,course_id))

    #Looks through first all submissions that are marked for instructor grading and are pending, then looks
    #through submissions that are marked for instructor or ML grading and are pending, then finally
    #looks through submisisons that have been marked finished and have been graded already by ML.
    for location in locations_for_course:
        success, sub_id = get_single_instructor_grading_item_for_location_with_options(location,check_for_ml=True)
        if success:
            return success, sub_id

    log.debug("ML models already created for all locations in this course.  Getting low confidence finished ML submissions.")

    for location in locations_for_course:
       success, sub_id = get_single_instructor_grading_item_for_location_with_options(location,check_for_ml=False,
           types_to_check_for="ML", submission_state_to_check_for=SubmissionState.finished)
       if success:
           return success, sub_id

    return found, sub_id

def set_instructor_grading_item_back_to_ml(submission_id):
    """
    Sets a submission from instructor grading to ML.
    Input:
        Submission id
    Output:
        Boolean success, submission or error message
    """
    success, sub=check_submission_id(submission_id)

    if not success:
        return success, sub

    log.debug("Setting back to ML.")
    grader_dict={
        'feedback' : 'Instructor skipped',
        'status' : GraderStatus.failure,
        'grader_id' : 1,
        'grader_type' : "IN",
        'confidence' : 1,
        'score' : 0,
        'errors' : "Instructor skipped the submission."
    }

    sub.next_grader_type="ML"
    sub.state=SubmissionState.waiting_to_be_graded
    sub.save()
    create_grader(grader_dict,sub)

    return True, sub

def check_submission_id(submission_id):

    if not isinstance(submission_id,Submission):
        try:
            sub=Submission.objects.get(id=submission_id)
        except:
            error_message="Could not find a submission id."
            log.exception(error_message)
            return False, error_message
    else:
        sub=submission_id

    return True, sub

def set_ml_grading_item_back_to_instructor(submission_id):
    """
    Sets a submission from ML grading to instructor without creating a grader object.
    Input:
        Submission id
    Output:
        Boolean success, submission or error message
    """
    success, sub=check_submission_id(submission_id)

    if not success:
        return success, sub

    log.debug("Setting back to Instructor.")
    sub.next_grader_type="IN"
    sub.state=SubmissionState.waiting_to_be_graded
    sub.save()

    return True, sub

def get_staff_grading_notifications(course_id):
    staff_needs_to_grade = False
    success = True

    unique_course_locations = [x['location'] for x in
                               Submission.objects.filter(course_id = course_id).values('location').distinct()]
    for location in unique_course_locations:
        min_scored_for_location=settings.MIN_TO_USE_PEER
        location_ml_count = Submission.objects.filter(location=location, preferred_grader_type="ML").count()
        if location_ml_count>0:
            min_scored_for_location=settings.MIN_TO_USE_ML

        location_scored_count = finished_submissions_graded_by_instructor(location).count()
        submissions_pending = submissions_pending_for_location(location).count()

        if location_scored_count<min_scored_for_location and submissions_pending>0:
            staff_needs_to_grade= True
            return success, staff_needs_to_grade

    return success, staff_needs_to_grade
