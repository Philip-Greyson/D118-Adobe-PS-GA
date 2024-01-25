"""Script to find users that are enrolled in certain courses and move them to custom OU.

https://github.com/Philip-Greyson/D118-Adobe-PS-GA

First looks at all students currently in the custom Adobe OU.
Finds all students in PS, then searches for a relevant course number in their enrollments.
Verifies students who match the course numbers, and moves them to the Adobe OU if they are not there already.
Finally removes any students in the custom Adobe OU that were not verified (no longer enrolled a course)

Needs the google-api-python-client, google-auth-httplib2 and the google-auth-oauthlib
pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib

See the following for table information
https://ps.powerschool-docs.com/pssis-data-dictionary/latest/cc-4-ver3-6-1
https://ps.powerschool-docs.com/pssis-data-dictionary/latest/terms-13-ver3-6-1
"""

# importing module
import datetime  # needed to get current date to check what term we are in
import os  # needed to get environment variables
from datetime import *

import oracledb  # needed for connection to PowerSchool (oracle database)
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# set up database connection info
un = os.environ.get('POWERSCHOOL_READ_USER')  # username for read-only database user
pw = os.environ.get('POWERSCHOOL_DB_PASSWORD')  # the password for the database account
cs = os.environ.get('POWERSCHOOL_PROD_DB')  # the IP address, port, and database name to connect to

print(f"DBUG: Username: {un} |Password: {pw} |Server: {cs}")  # debug so we can see where oracle is trying to connect to/with

# define a list of the OUs where the Adobe licensed students are found, so that we can go through them and remove any students that should not be there
# need to have the orgUnit enclosed by its own set of quotes in order to work
ADOBE_OUS = ["'/D118 Students/WHS Students/Adobe Licensed Students'","'/D118 Students/WMS Students/Adobe Licensed Students'","'/D118 Students/MMS Students/Adobe Licensed Students'"]
ADOBE_OU_SUFFIX = "/Adobe Licensed Students"  # the custom OU string that will follow their current building level OU
# define our grade groups (in our case middle school 6-8 and high school 9-12) and the class codes to look for in those buildings
GROUP1_GRADE_MINIMUM = 6
GROUP1_GRADE_MAXIMUM = 8
GROUP1_CLASSES = ['EX6ART', 'EX7ART', 'EX8ART']  # list of course numbers to search for, must match exactly
GROUP2_GRADE_MINIMUM = 9
GROUP2_GRADE_MAXIMUM = 12
GROUP2_CLASSES = ['163', '148', '137', '985', '164']  # list of course numbers to search for, must match exactly

# Google API Scopes that will be used. If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/admin.directory.user', 'https://www.googleapis.com/auth/admin.directory.group', 'https://www.googleapis.com/auth/admin.directory.group.member', 'https://www.googleapis.com/auth/admin.directory.orgunit', 'https://www.googleapis.com/auth/admin.directory.userschema']

# Get credentials from json file, ask for permissions on scope or use existing token.json approval, then build the "service" connection to Google API
creds = None
# The file token.json stores the user's access and refresh tokens, and is
# created automatically when the authorization flow completes for the first
# time.
if os.path.exists('token.json'):
    creds = Credentials.from_authorized_user_file('token.json', SCOPES)
# If there are no (valid) credentials available, let the user log in.
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)
    # Save the credentials for the next run
    with open('token.json', 'w') as token:
        token.write(creds.to_json())

service = build('admin', 'directory_v1', credentials=creds)


if __name__ == '__main__':  # main file execution
    with open('adobe_log.txt', 'w', encoding='utf-8') as log:  # open logging file
        startTime = datetime.now()
        startTime = startTime.strftime('%H:%M:%S')
        print(f'INFO: Execution started at {startTime}')
        print(f'INFO: Execution started at {startTime}', file=log)
        with oracledb.connect(user=un, password=pw, dsn=cs) as con:  # create the connecton to the database
            with con.cursor() as cur:  # start an entry cursor
                print("Connection established: " + con.version)
                print("Connection established: " + con.version, file=log)
                today = datetime.now()  # get todays date and store it for finding the correct term later
                # print("today = " + str(today))  # debug
                # print("today = " + str(today), file=log)  # debug

                # Get a list of students that are in the Adobe OUs so we can remove anyone that should not be there later
                adobeOUStudents = {}  # create blank dictionary, will have their emails and whether they should be removed later
                for OU in ADOBE_OUS:
                    userToken =  ''
                    queryString = f"orgUnitPath={OU}"  # have to have the orgUnit enclosed by its own set of quotes in order to work
                    while userToken is not None:  # do a while loop while we still have the next page token to get more results with
                        userResults = service.users().list(customer='my_customer', orderBy='email', projection='full', pageToken=userToken, query=queryString).execute()
                        userToken = userResults.get('nextPageToken')
                        users = userResults.get('users', [])
                        for user in users:  # go through each user profile
                            adobeOUStudents.update({user.get('primaryEmail') : 'Invalid'})  # get the primary email of the user, append it to the list of students in the OU, leave second associated field blank
                    # print(adobeOUStudents, file=log)

                # do the sql query on students getting required info to get the course enrollments
                cur.execute('SELECT student_number, dcid, id, schoolid, enroll_status, grade_level FROM students ORDER BY student_number DESC')
                students = cur.fetchall()
                for student in students:  # go through each student
                    try:
                        idNum = str(int(student[0]))  # the student number usually referred to as their "id number"
                        stuDCID = str(student[1])  # the student dcid
                        internalID = int(student[2])  # get the internal id of the student that is referenced in the classes entries
                        status = str(student[4])  # enrollment status, 0 for active
                        schoolID = int(student[3])  # schoolcode
                        grade = int(student[5])  # grade level
                        email = idNum + "@d118.org"
                        # print(f'Student {idNum} in grade {grade} at building {schoolID}', file=log) # debug
                        if (status == '0' and schoolID != 901 and (grade in range(GROUP1_GRADE_MINIMUM,GROUP2_GRADE_MAXIMUM+1))):  # only active students in 6-12 not in pre-registered will get processed, otherwise just skipped
                            #do another query to get their terms to find the current term
                            try:
                                 # get a list of terms for the school so we can find courses for those terms, filtering to not full years. Use bind variables. https://python-oracledb.readthedocs.io/en/latest/user_guide/bind.html#bind
                                cur.execute("SELECT id, firstday, lastday, schoolid, dcid FROM terms WHERE schoolid = :school ORDER BY dcid DESC", school = schoolID)
                                terms = cur.fetchall()
                                for termEntry in terms:  # go through every term result
                                    #compare todays date to the start and end dates with 2 days before start so it populates before the first day of the term
                                    if ((termEntry[1] - timedelta(days=2) < today) and (termEntry[2] + timedelta(days=1) > today)):
                                        termid = str(termEntry[0])
                                        termDCID = str(termEntry[4])
                                        # print(f"DBUG: Found good term for student {idNum} at building {schoolID} : {termid} | {termDCID}")  # debug
                                        # print(f"DBUG: Found good term for student {idNum} at building {schoolID} : {termid} | {termDCID}", file=log)  # debug
                                        print(f'DBUG: Starting student {idNum} at building {schoolID} in term {termid}')
                                        print(f'DBUG: Starting student {idNum} at building {schoolID} in term {termid}', file=log)

                                        userClasses = []  # make empty list for storing of the classes that match our queries
                                        # do the query of their courses for the current term, filter to match certain courses
                                        if grade in range(GROUP1_GRADE_MINIMUM, GROUP1_GRADE_MAXIMUM+1):  # if they are in group 1 (middle school). Need to add 1 for the top of range since it excludes the max value
                                            for classCode in GROUP1_CLASSES:
                                                # print(f'DBUG: {idNum} is a middle schooler, looking for course number {classCode}')  # debug
                                                # print(f'DBUG: {idNum} is a middle schooler, looking for course number {classCode}', file=log)  # debug
                                                # do our query for the current student, the course number and the current term. Use bind variables. https://python-oracledb.readthedocs.io/en/latest/user_guide/bind.html#bind
                                                cur.execute("SELECT cc.schoolid, cc.course_number, cc.sectionid, cc.section_number, cc.termid, cc.expression, courses.course_name FROM cc LEFT JOIN courses ON cc.course_number = courses.course_number WHERE cc.course_number = :course AND cc.studentid = :studentInternalID AND cc.termid = :termid ORDER BY cc.course_number", course = classCode, studentInternalID = internalID, termid = termid)
                                                currentClassResults = cur.fetchall()  # fetch the results of our class query
                                                userClasses = userClasses + currentClassResults  # append the current results to our total results so we do not overwrite any found classes with blanks
                                        elif grade in range (GROUP2_GRADE_MINIMUM, GROUP2_GRADE_MAXIMUM+1):  # if they are in group 2 (high school). Need to add 1 for the top of range since it excludes the max value
                                            for classCode in GROUP2_CLASSES:
                                                # print(f'DBUG: {idNum} is a high schooler, looking for course number {classCode}')  # debug
                                                # print(f'DBUG: {idNum} is a high schooler, looking for course number {classCode}', file=log)  # debug
                                                # do our query for the current student, the course number and the current term. Use bind variables. https://python-oracledb.readthedocs.io/en/latest/user_guide/bind.html#bind
                                                cur.execute("SELECT cc.schoolid, cc.course_number, cc.sectionid, cc.section_number, cc.termid, cc.expression, courses.course_name FROM cc LEFT JOIN courses ON cc.course_number = courses.course_number WHERE cc.course_number = :course AND cc.studentid = :studentInternalID AND cc.termid = :termid ORDER BY cc.course_number", course = classCode, studentInternalID = internalID, termid = termid)
                                                currentClassResults = cur.fetchall()  # fetch the results of our class query
                                                userClasses = userClasses + currentClassResults  # append the current results to our total results so we do not overwrite any found classes with blanks
                                        # print(userClasses, file=log)  # debug, quickly fills up the log
                                        if userClasses:  # if there are results of the class query
                                            adobeOUStudents.update({email: 'Valid'})  # update the user entry in the adobeOUStudents dictionary to say they are valid, and not remove them from the OU. If they do not exist it will add them
                                            for entry in userClasses:  # go through each class that matches to print it out
                                                # print(entry)
                                                className = entry[6]
                                                courseNumber = entry[1]
                                                # print(entry, file=log) # debug
                                                print(f'INFO: Student {idNum} is enrolled in course number {courseNumber} named "{className}" at building {schoolID} for the current term {termid}')
                                                print(f'INFO: Student {idNum} is enrolled in course number {courseNumber} named "{className}" at building {schoolID} for the current term {termid}', file=log)

                                            # next do a query in Google Admin for the students account based on their email
                                            queryString = 'email=' + email  # construct the query string which looks for the email
                                            userToUpdate = service.users().list(customer='my_customer', domain='d118.org', maxResults=2, orderBy='email', projection='full', query=queryString).execute()  # return a list of at most 2 users
                                            if userToUpdate.get('users'):  # if we found a user in Google that matches the user email
                                                bodyDict = {}  # define empty dict that will hold the update parameters
                                                currentOU = userToUpdate.get('users')[0].get('orgUnitPath')
                                                # print(f'{email} is currently in {currentOU}', file=log) # debug
                                                buildingOU = currentOU.split('/')[0] + '/' + currentOU.split('/')[1] + '/' + currentOU.split('/')[2]  # reconstruct just their building OU with no grade level by splitting the current OU and re-adding the parts together
                                                adobeOU = buildingOU + ADOBE_OU_SUFFIX
                                                if currentOU != adobeOU:
                                                    print(f'ACTION: User {email} will to be moved from {currentOU} to {adobeOU}')
                                                    print(f'ACTION: User {email} will to be moved from {currentOU} to {adobeOU}', file=log)
                                                    bodyDict.update({'orgUnitPath' : adobeOU})  # add OU to body of the update

                                                # Finally, do the actual update of the user profile, using the bodyDict we have constructed in the above sections
                                                if bodyDict:  # if there is anything in the body dict we want to update. if its empty we skip the update
                                                    try:
                                                        # print(bodyDict) # debug
                                                        # print(bodyDict, file=log) # debug
                                                        outcome = service.users().update(userKey = email, body=bodyDict).execute()  # does the actual updating of the user profile
                                                    except Exception as er:
                                                        print(f'ERROR: cannot update {email} : {er}')
                                                        print(f'ERROR: cannot update {email} : {er}', file=log)
                                            else:
                                                print(f'ERROR: Student {email} does not exist in Google Admin, cannot add them to the OU!')
                                                print(f'ERROR: Student {email} does not exist in Google Admin, cannot add them to the OU!', file=log)


                            except Exception as er:
                                print(f'ERROR getting courses for {idNum}: {er}')
                                print(f'ERROR getting courses for {idNum}: {er}', file=log)

                    except Exception as er:
                        print(f'ERROR on {student[0]}: {er}')
                        print(f'ERROR on {student[0]}: {er}', file=log)

                # print(adobeOUStudents, file=log) # debug
                # Now go through the AdobeOUStudents dict, and if the user is marked as Invalid still, remove them from the Adobe OU
                for email, status in adobeOUStudents.items():
                    if status == 'Invalid':
                        print(f'WARN: Student {email} should no longer be in the Adobe OU')
                        print(f'WARN: Student {email} should no longer be in the Adobe OU', file=log)

                        # next do a query in Google Admin for the students account based on their email
                        queryString = 'email=' + email  # construct the query string which looks for the email
                        userToUpdate = service.users().list(customer='my_customer', domain='d118.org', maxResults=2, orderBy='email', projection='full', query=queryString).execute()  # return a list of at most 2 users
                        if userToUpdate.get('users'):  # if we found a user in Google that matches the user email
                            bodyDict = {}  # define empty dict that will hold the update parameters
                            currentOU = userToUpdate.get('users')[0].get('orgUnitPath')
                            # print(f'{email} is currently in {currentOU}', file=log) # debug
                            buildingOU = currentOU.split('/')[0] + '/' + currentOU.split('/')[1] + '/' + currentOU.split('/')[2]  # reconstruct just their building OU with no grade level by splitting the current OU and re-adding the parts together
                            print(f'ACTION: User {email} will to be moved from {currentOU} to {buildingOU}')
                            print(f'ACTION: User {email} will to be moved from {currentOU} to {buildingOU}', file=log)
                            bodyDict.update({'orgUnitPath' : buildingOU})  # add OU to body of the update

                            # Finally, do the actual update of the user profile, using the bodyDict we have constructed in the above sections
                            if bodyDict:  # if there is anything in the body dict we want to update. if its empty we skip the update
                                try:
                                    # print(bodyDict) # debug
                                    # print(bodyDict, file=log) # debug
                                    outcome = service.users().update(userKey = email, body=bodyDict).execute()  # does the actual updating of the user profile
                                except Exception as er:
                                    print(f'ERROR: cannot update {email} : {er}')
                                    print(f'ERROR: cannot update {email} : {er}', file=log)
