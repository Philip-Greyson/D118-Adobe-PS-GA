# See the following for table information
# https://ps.powerschool-docs.com/pssis-data-dictionary/latest/cc-4-ver3-6-1
# https://docs.powerschool.com/PSDD/powerschool-tables/terms-13-ver3-6-1

# Needs the google-api-python-client, google-auth-httplib2 and the google-auth-oauthlib
# pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib

# importing module
import oracledb # needed for connection to PowerSchool (oracle database)
import sys # needed for non scrolling text output
import datetime # needed to get current date to check what term we are in
import os # needed to get environment variables
import pysftp # needed for sftp file upload
from datetime import *
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# set up database connection info
un = 'PSNavigator' #PSNavigator is read only, PS is read/write
pw = os.environ.get('POWERSCHOOL_DB_PASSWORD') #the password for the PSNavigator account
cs = os.environ.get('POWERSCHOOL_PROD_DB') #the IP address, port, and database name to connect to

print("Username: " + str(un) + " |Password: " + str(pw) + " |Server: " + str(cs)) #debug so we can see where oracle is trying to connect to/with

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

# create the connecton to the database
with oracledb.connect(user=un, password=pw, dsn=cs) as con:
    with con.cursor() as cur:  # start an entry cursor
        with open('adobe_log.txt', 'w') as log:  # open the logging file
            print("Connection established: " + con.version)
            print("Connection established: " + con.version, file=log)
            today = datetime.now() #get todays date and store it for finding the correct term later
            print("today = " + str(today))  # debug
            print("today = " + str(today), file=log)  # debug

            # Get a list of students that are in the Adobe OUs so we can remove anyone that should not be there later
            adobeOUStudents = {} # create blank dictionary, will have their emails and whether they should be removed later
            userToken =  ''
            queryString = "orgUnitPath='/D118 Students/WHS Students/Adobe Licensed Students'" # have to have the orgUnit enclosed by its own set of quotes in order to work
            while userToken is not None: # do a while loop while we still have the next page token to get more results with
                userResults = service.users().list(customer='my_customer', orderBy='email', projection='full', pageToken=userToken, query=queryString).execute()
                userToken = userResults.get('nextPageToken')
                users = userResults.get('users', [])
                for user in users: # go through each user profile
                    adobeOUStudents.update({user.get('primaryEmail') : 'Invalid'}) # get the primary email of the user, append it to the list of students in the OU, leave second associated field blank
            # print(adobeOUStudents, file=log)

            # do the sql query on students getting required info to get the course enrollments
            cur.execute('SELECT student_number, dcid, id, schoolid, enroll_status, grade_level FROM students ORDER BY student_number DESC')
            rows = cur.fetchall()
            for count, student in enumerate(rows): # go through each student
                try:
                    sys.stdout.write('\rProccessing student entry %i' % count) # sort of fancy text to display progress of how many students are being processed without making newlines
                    sys.stdout.flush()

                    idNum = str(int(student[0])) # the student number usually referred to as their "id number"
                    stuDCID = str(student[1]) # the student dcid
                    internalID = int(student[2]) #get the internal id of the student that is referenced in the classes entries
                    status = str(student[4]) # enrollment status, 0 for active
                    schoolID = int(student[3]) # schoolcode
                    grade = int(student[5]) # grade level
                    email = idNum + "@d118.org"
                    # print(f'Student {idNum} in grade {grade} at building {schoolID}', file=log) # debug
                    if (status == '0' and schoolID != 901 and (grade in range(6,12))): # only active students in 6-12 not in pre-registered will get processed, otherwise just skipped
                        #do another query to get their terms to find the current term
                        try:
                            cur.execute("SELECT id, firstday, lastday, schoolid, dcid FROM terms WHERE schoolid = " + str(schoolID) + " ORDER BY dcid DESC")  # get a list of terms for the school, filtering to not full years
                            terms = cur.fetchall()
                            for termEntry in terms:  # go through every term result
                                #compare todays date to the start and end dates with 2 days before start so it populates before the first day of the term
                                if ((termEntry[1] - timedelta(days=2) < today) and (termEntry[2] + timedelta(days=1) > today)):
                                    termid = str(termEntry[0])
                                    termDCID = str(termEntry[4])
                                    # print("Found good term for student " + str(idNum) + ": " + termid + " | " + termDCID)
                                    # print(f"Found good term for student {idNum} at building {schoolID} : {termid} | {termDCID}", file=log) # debug

                                    # do the query of their courses for the current term, filter to match certain courses
                                    if grade in range(9,12): # if they are in high school
                                        # print(f'{idNum} is a high schooler, looking for course numbers 137, 148, 163', file=log) # debug
                                        cur.execute("SELECT cc.schoolid, cc.course_number, cc.sectionid, cc.section_number, cc.termid, cc.expression, courses.course_name FROM cc LEFT JOIN courses ON cc.course_number = courses.course_number WHERE (cc.course_number = '163' OR cc.course_number = '148' OR cc.course_number = '137') AND cc.studentid = " + str(internalID) + " AND cc.termid = " + termid + " ORDER BY cc.course_number")
                                    elif grade in range (6,8): # if they are in middle school, search for an ART in the course number
                                        # print(f'{idNum} is a middle schooler, looking for an ART class', file=log) # debug
                                        cur.execute("SELECT cc.schoolid, cc.course_number, cc.sectionid, cc.section_number, cc.termid, cc.expression, courses.course_name FROM cc LEFT JOIN courses ON cc.course_number = courses.course_number WHERE (instr(cc.course_number, 'ART') > 0) AND cc.studentid = " + str(internalID) + " AND cc.termid = " + termid + " ORDER BY cc.course_number")
                                    userClasses = cur.fetchall()
                                    # print(userClasses, file=log) # debug, quickly fills up the log
                                    if userClasses: # if there are results of the class query
                                        adobeOUStudents.update({email: 'Valid'}) # update the user entry in the adobeOUStudents dictionary to say they are valid, and not remove them from the OU
                                        for entry in userClasses: # go through each class that matches
                                            # print(entry)
                                            className = entry[6]
                                            # print(entry, file=log) # debug
                                            print(f'INFO: Student {idNum} is enrolled in "{className}" at building {schoolID} for the current term {termid}', file=log)

                                            # next do a query in Google Admin for the students account based on their email
                                            queryString = 'email=' + email # construct the query string which looks for the email
                                            userToUpdate = service.users().list(customer='my_customer', domain='d118.org', maxResults=2, orderBy='email', projection='full', query=queryString).execute() # return a list of at most 2 users
                                            if userToUpdate.get('users'): # if we found a user in Google that matches the user email
                                                bodyDict = {} # define empty dict that will hold the update parameters
                                                currentOU = userToUpdate.get('users')[0].get('orgUnitPath')
                                                # print(f'{email} is currently in {currentOU}', file=log) # debug
                                                buildingOU = currentOU.split('/')[0] + '/' + currentOU.split('/')[1] + '/' + currentOU.split('/')[2] # reconstruct just their building OU with no grade level by splitting the current OU and re-adding the parts together
                                                adobeOU = buildingOU + '/Adobe Licensed Students'
                                                if currentOU != adobeOU:
                                                    print(f'ACTION: User {email} will to be moved from {currentOU} to {adobeOU}')
                                                    print(f'ACTION: User {email} will to be moved from {currentOU} to {adobeOU}', file=log)
                                                    bodyDict.update({'orgUnitPath' : adobeOU}) # add OU to body of the update

                                                # Finally, do the actual update of the user profile, using the bodyDict we have constructed in the above sections
                                                if bodyDict: # if there is anything in the body dict we want to update. if its empty we skip the update
                                                    try:
                                                        # print(bodyDict) # debug
                                                        # print(bodyDict, file=log) # debug
                                                        outcome = service.users().update(userKey = email, body=bodyDict).execute() # does the actual updating of the user profile
                                                    except Exception as er:
                                                        print(f'ERROR: cannot update {email} : {er}')
                                                        print(f'ERROR: cannot update {email} : {er}', file=log)
                                            else:
                                                print(f'ERROR: Student {email} does not exist in Google Admin, cannot add them to the OU!')
                                                print(f'ERROR: Student {email} does not exist in Google Admin, cannot add them to the OU!', file=log)
                                                


                                    

                        except Exception as er:
                            print('Error getting courses on ' + str(idNum) + ': ' + str(er))

                except Exception as er:
                    print('Error on ' + str(student[0]) + ': ' + str(er))

            # print(adobeOUStudents, file=log) # debug
            # Now go through the AdobeOUStudents dict, and if the user is marked as Invalid still, remove them from the Adobe OU
            for email, status in adobeOUStudents.items():
                if status == 'Invalid':
                    print(f'WARN: Student {email} should no longer be in the Adobe OU')
                    print(f'WARN: Student {email} should no longer be in the Adobe OU', file=log)

                    # next do a query in Google Admin for the students account based on their email
                    queryString = 'email=' + email # construct the query string which looks for the email
                    userToUpdate = service.users().list(customer='my_customer', domain='d118.org', maxResults=2, orderBy='email', projection='full', query=queryString).execute() # return a list of at most 2 users
                    if userToUpdate.get('users'): # if we found a user in Google that matches the user email
                        bodyDict = {} # define empty dict that will hold the update parameters
                        currentOU = userToUpdate.get('users')[0].get('orgUnitPath')
                        # print(f'{email} is currently in {currentOU}', file=log) # debug
                        buildingOU = currentOU.split('/')[0] + '/' + currentOU.split('/')[1] + '/' + currentOU.split('/')[2] # reconstruct just their building OU with no grade level by splitting the current OU and re-adding the parts together
                        print(f'ACTION: User {email} will to be moved from {currentOU} to {buildingOU}')
                        print(f'ACTION: User {email} will to be moved from {currentOU} to {buildingOU}', file=log)
                        bodyDict.update({'orgUnitPath' : buildingOU}) # add OU to body of the update

                        # Finally, do the actual update of the user profile, using the bodyDict we have constructed in the above sections
                        if bodyDict: # if there is anything in the body dict we want to update. if its empty we skip the update
                            try:
                                # print(bodyDict) # debug
                                # print(bodyDict, file=log) # debug
                                outcome = service.users().update(userKey = email, body=bodyDict).execute() # does the actual updating of the user profile
                            except Exception as er:
                                print(f'ERROR: cannot update {email} : {er}')
                                print(f'ERROR: cannot update {email} : {er}', file=log)
