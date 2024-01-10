
# D118-Adobe-PS-GA

Finds students that are enrolled in specific courses in PowerSchool and moves them to a special OU in Google Admin for use in the Adobe licensing process. When they are no longer enrolled in one of these courses they are moved back to the normal OU for their building.

## Overview

The purpose of this script is to move students who are enrolled in specific courses in PowerSchool into special Google organizational units. Then these organizational units are used in the Adobe admin console to provide licensing for Adobe products for only the students who need them for their current classes. When they are no longer in the class, they are removed from the organizational unit so the license is cleared. This allows for a smaller number of Adobe licenses to be purchased instead of having enough for entire buildings or for every student when it is not necessary.  

The script starts by first finding all students currently in the special Adobe Organizational Units (OUs) and marking them as "invalid" until later processed. If they are found to still be enrolled, their entry is marked valid later and they will not be removed from the special OU.
Then a query is done for all students in PowerSchool getting the basic information that is needed to find their courses like school, grade level, internal ID, etc.
The students are then processed one at a time, the current date is compared to terms from the terms table to find one that is currently active. Once a valid term is found, a query is made for courses that have a course number that match a defined list of course numbers that is based on their grade levels - in our case just art classes for the middle schools and additional design classes for high schoolers.
If they are found to be enrolled in one of these classes, their entry is marked valid in the initial membership list, and a query is done on their Google account to check the OU membership. If they are not in the special OU which is under their building level OU, they are moved to it.
Finally, the membership is gone through to see if there are any students still marked invalid, meaning they should no longer be in the Adobe OU. If any are found, they are moved back to their building OU.

## Requirements

The following Environment Variables must be set on the machine running the script:

- POWERSCHOOL_READ_USER
- POWERSCHOOL_DB_PASSWORD
- POWERSCHOOL_PROD_DB

These are fairly self explanatory, and just relate to the usernames, passwords, and host IP/URLs for PowerSchool. If you wish to directly edit the script and include these credentials, you can.

Additionally, the following Python libraries must be installed on the host machine (links to the installation guide):

- [Python-oracledb](https://python-oracledb.readthedocs.io/en/latest/user_guide/installation.html)
- [Python-Google-API](https://github.com/googleapis/google-api-python-client#installation)

In addition, an OAuth credentials.json file must be in the same directory as the overall script. This is the credentials file you can download from the Google Cloud Developer Console under APIs & Services > Credentials > OAuth 2.0 Client IDs. Download the file and rename it to credentials.json. When the program runs for the first time, it will open a web browser and prompt you to sign into a Google account that has the permissions to disable, enable, deprovision, and move the devices. Based on this login it will generate a token.json file that is used for authorization. When the token expires it should auto-renew unless you end the authorization on the account or delete the credentials from the Google Cloud Developer Console. One credentials.json file can be shared across multiple similar scripts if desired.
There are full tutorials on getting these credentials from scratch available online. But as a quickstart, you will need to create a new project in the Google Cloud Developer Console, and follow [these](https://developers.google.com/workspace/guides/create-credentials#desktop-app) instructions to get the OAuth credentials, and then enable APIs in the project (the Admin SDK API is used in this project).

## Customization

This script is very customized to our school district as it uses searches for specific course "numbers" which correlate to our art and design classes, as well as making some assumptions on how the Google OUs are set up. It will require a bit of coding to change this to work with your specific district, but some things you will likely want to change are listed below:

- `ADOBE_OUS` is the list of Google OUs that contain the current students who have the Adobe licenses. These will need to be changed to match whatever OUs you decide to use
- `ADOBE_OU_SUFFIX` can be changed if you use a similar OU structure to ours where we have overall students > building > grade levels. The suffix takes the place of the grade levels and can be changed to have a different name
  - If you want to process this OU creation differently, look at the lines starting with `buildingOU =` and `adobeOU =` for both the move in and move out blocks to change how this OU string is constructed
- The classes that are searched for and the grade levels that are used for each group are controlled by the `GROUP1_CLASSES`, `GROUP2_CLASSES`, `GROUP1_GRADE_MINIMUM`, `GROUP1_GRADE_MAXIMUM`, `GROUP2_GRADE_MINIMUM` and `GROUP2_GRADE_MAXIMUM`. These are fairly self explanatory, the grade minimum and maximums are the grade levels to search between - in our case 6-8 and 9-12. Then the classes lists are the course numbers to search for in those groups.
  - If you want to add additional groups you will need to add another `elif grade in range(x, y):` using whatever grades you want, copy and paste the other `elif` block but replace the GROUP2_CLASSES and with a new list of classes.
