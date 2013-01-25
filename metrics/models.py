from django.db import models
from controller.models import GRADER_TYPE, STATUS_CODES, STATE_CODES
from django.utils import timezone

CHARFIELD_LEN_SMALL=128
CHARFIELD_LEN_LONG = 1024

class Timing(models.Model):

    #The need to store all of this could be solved by putting a foreign key on a submission object.
    #However, the point of not doing that is twofold:
    #1.  We want to keep this as separate as possible to we can switch to something else down the line.
    #2.  We don't want to tie up the main working submission and grader tables with queries.

    #Actual timing
    start_time=models.DateTimeField(auto_now_add=True)
    end_time=models.DateTimeField(blank=True, null=True, default=timezone.now)
    finished_timing=models.BooleanField(default=False)

    #Essay metadata
    student_id=models.CharField(max_length=CHARFIELD_LEN_SMALL)
    location=models.CharField(max_length=CHARFIELD_LEN_SMALL, db_index = True)
    problem_id=models.CharField(max_length=CHARFIELD_LEN_LONG)
    course_id=models.CharField(max_length=CHARFIELD_LEN_SMALL)
    max_score=models.IntegerField(default=1)

    #This is so that we can query on it if we need to get more data
    submission_id=models.IntegerField(blank=True,null=True)

    #Grader Metadata
    grader_type=models.CharField(max_length=2,choices=GRADER_TYPE,null=True, blank=True)
    status_code = models.CharField(max_length=1, choices=STATUS_CODES,null=True, blank=True)
    confidence = models.DecimalField(max_digits=10, decimal_places=9,null=True, blank=True)
    is_calibration = models.BooleanField(default=False)
    score=models.IntegerField(null=True, blank=True)

    #Badly named, but it can't be grader_id for obvious reasons!
    #This contains the version # of the grader.  For humans, version number is the lms id for the person.
    grader_version=models.CharField(max_length=CHARFIELD_LEN_LONG,null=True, blank=True)

    #This is so that we can query on it if we need to get more data
    grader_id=models.IntegerField(blank=True,null=True)

class StudentProfile(models.Model):
    student_id = models.CharField(max_length=CHARFIELD_LEN_SMALL, db_index = True)

    #Message data
    messages_sent = models.IntegerField()
    messages_received = models.IntegerField()
    average_message_feedback_length = models.IntegerField()

class StudentCourseProfile(models.Model):
    student_profile = models.ForeignKey('StudentProfile')

    #Attempt data
    problems_attempted = models.IntegerField(default=0)
    attempts_per_problem = models.DecimalField(max_digits=10, decimal_places=9, default=0)
    graders_per_attempt = models.DecimalField(max_digits=10, decimal_places=9, default=0)

    #Score data
    stdev_percent_score = models.DecimalField(max_digits=10, decimal_places=9, default=0)
    average_percent_score = models.DecimalField(max_digits=10, decimal_places=9, default=0)
    average_percent_score_last20 = models.DecimalField(max_digits=10, decimal_places=9, default=0)
    average_percent_score_last10 = models.DecimalField(max_digits=10, decimal_places=9, default=0)

    #Peer grading data
    problems_attempted_peer = models.IntegerField()
    completed_peer_grading = models.IntegerField(default=0)
    average_length_of_peer_feedback_given = models.DecimalField(max_digits=10, decimal_places=9, default=0)
    stdev_length_of_peer_feedback_given = models.DecimalField(max_digits=10, decimal_places=9, default=0)
    average_peer_grading_score_given = models.DecimalField(max_digits=10, decimal_places=9, default=0)
    attempts_per_problem_peer = models.DecimalField(max_digits=10, decimal_places=9, default=0)
    average_percent_score_peer = models.DecimalField(max_digits=10, decimal_places=9, default=0)

    #ML grading data
    problems_attempted_ml = models.IntegerField()
    attempts_per_problem_ml = models.DecimalField(max_digits=10, decimal_places=9, default=0)
    average_ml_confidence = models.DecimalField(max_digits=10, decimal_places=9, default=0)
    average_percent_score_ml = models.DecimalField(max_digits=10, decimal_places=9, default=0)

    #Submission data
    average_submission_length = models.IntegerField()
    stdev_submission_length = models.DecimalField(max_digits=10, decimal_places=9, default=0)



