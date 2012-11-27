"""
Run me with:
    python manage.py test --settings=xqueue.test_settings queue
"""
import json
import unittest
from datetime import datetime
import logging
import urlparse

from django.contrib.auth.models import User
from django.test.client import Client
import requests
from django.conf import settings

import xqueue_interface
import grader_interface
import util

from models import Submission, Grader
from models import GraderStatus, SubmissionState

log = logging.getLogger(__name__)

LOGIN_URL = "/grading_controller/login/"
SUBMIT_URL = "/grading_controller/submit/"
ML_GET_URL = "/grading_controller/get_submission_ml/"
IN_GET_URL = "/grading_controller/get_submission_instructor/"
PUT_URL="/grading_controller/put_result/"

TEST_SUB = Submission(
    prompt="prompt",
    student_id="id",
    problem_id="id",
    state=SubmissionState.waiting_to_be_graded,
    student_response="response",
    student_submission_time=datetime.now(),
    xqueue_submission_id="id",
    xqueue_submission_key="key",
    xqueue_queue_name="MITx-6.002x",
    location="location",
    course_id="course_id",
    max_score=3,
    next_grader_type="IN",
)

def parse_xreply(xreply):

    xreply = json.loads(xreply)
    if 'success' in xreply:
        return_code=xreply['success']
    elif 'return_code' in xreply:
        return_code = (xreply['return_code']==0)
    else:
        return_code = False

    return (return_code, xreply['content'])


def login_to_controller(session):
    controller_login_url = urlparse.urljoin(settings.GRADING_CONTROLLER_INTERFACE['url'], LOGIN_URL)

    response = session.post(controller_login_url,
        {'username': 'test',
         'password': 'CambridgeMA',
        }
    )
    response.raise_for_status()
    log.debug(response.content)
    return True


class XQueueInterfaceTest(unittest.TestCase):
    def setUp(self):
        if(User.objects.filter(username='test').count() == 0):
            user = User.objects.create_user('test', 'test@test.com', 'CambridgeMA')
            user.save()
        self.c = Client()

    def test_log_in(self):
        '''
        Test Xqueue login behavior. Particularly important is the response for GET (e.g. by redirect)
        '''

        # 0) Attempt login with GET, must fail with message='login_required'
        #    The specific message is important, as it is used as a flag by LMS to reauthenticate!
        response = self.c.get(LOGIN_URL)
        (error, msg) = parse_xreply(response.content)
        self.assertEqual(error, False)

        # 1) Attempt login with POST, but no auth
        response = self.c.post(LOGIN_URL)
        (error, _) = parse_xreply(response.content)
        self.assertEqual(error, False)

        # 2) Attempt login with POST, incorrect auth
        response = self.c.post(LOGIN_URL, {'username': 'test', 'password': 'PaloAltoCA'})
        (error, _) = parse_xreply(response.content)
        self.assertEqual(error, False)

        # 3) Login correctly
        response = self.c.post(LOGIN_URL, {'username': 'test', 'password': 'CambridgeMA'})
        (error, _) = parse_xreply(response.content)
        self.assertEqual(error, True)

    def test_xqueue_submit(self):
        xqueue_header = {
            'submission_id': 1,
            'submission_key': 1,
            'queue_name': "MITx-6.002x",
        }
        grader_payload = {
            'location': u'MITx/6.002x/problem/OETest',
            'course_id': u'MITx/6.002x',
            'problem_id': u'6.002x/Welcome/OETest',
            'grader': "temp",
            'prompt' : 'This is a prompt',
            'rubric' : 'This is a rubric.',
            'grader_settings' : "ml_grading.conf",
        }
        student_info = {
            'submission_time': datetime.now().strftime("%Y%m%d%H%M%S"),
            'anonymous_student_id': "blah"
        }
        xqueue_body = {
            'grader_payload': json.dumps(grader_payload),
            'student_info': json.dumps(student_info),
            'student_response': "Test!",
            'max_score': 1,
        }
        content = {
            'xqueue_header': json.dumps(xqueue_header),
            'xqueue_body': json.dumps(xqueue_body),
        }

        response = self.c.login(username='test', password='CambridgeMA')

        content = self.c.post(
            SUBMIT_URL,
            content,
        )

        log.debug(content)

        body = json.loads(content.content)

        self.assertEqual(body['success'], True)


class GraderInterfaceTest(unittest.TestCase):
    def setUp(self):
        if(User.objects.filter(username='test').count() == 0):
            user = User.objects.create_user('test', 'test@test.com', 'CambridgeMA')
            user.save()

        self.c = Client()
        response = self.c.login(username='test', password='CambridgeMA')

    def test_submission_create(self):
        sub = TEST_SUB
        sub.save()
        assert True

    def test_get_ml_subs(self):
        content = self.c.get(
            ML_GET_URL,
            data={}
        )

        body = json.loads(content.content)
        log.debug(body)
        self.assertEqual(body['error'], "Nothing to grade.")
        self.assertEqual(body['success'], False)

    def test_get_sub_in(self):
        sub = TEST_SUB
        sub.save()

        content = self.c.get(
            IN_GET_URL,
            data={'course_id': 'course_id'}
        )

        body = json.loads(content.content)

        sub_id = body['submission_id']

        return_code = body['success']
        self.assertEqual(return_code, True)

        sub = Submission.objects.get(id=sub_id)

        self.assertEqual(sub.prompt, "prompt")

    def test_put_result(self):

        post_dict={
            'feedback': "test feedback",
            'submission_id' : 1 ,
            'grader_type' : "ML" ,
            'status' : "S",
            'confidence' : 1,
            'grader_id' : 1,
            'score' : 1,
            }

        content = self.c.post(
            PUT_URL,
            post_dict,
        )

        body=json.loads(content.content)

        log.debug(body)
        return_code=body['success']

        self.assertEqual(return_code,True)



