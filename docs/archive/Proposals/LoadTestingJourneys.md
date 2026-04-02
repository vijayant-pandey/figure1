
# User Journeys

Information on how typical user journeys can be approximated with API calls


## Feed/Case Browsing:

**Description:** Most common path for the majority of users.  Involves browsing through cases in various feeds and searches

1. Load initial feed (recommended for you)

    `POST /pro/v1/feeds/{user_uid}`
    ```
    {
        "feed_type_uuid": "00451d3e-1a4c-4dfe-9fd0-344938afc7b2"
    }
    ```

1. _[Delay 30s-2m]_ User scrolls down, loads next page in feed

    `POST /pro/v1/feeds/{user_uid}/update`
    ```
    {
        "feed_type_uuid": "00451d3e-1a4c-4dfe-9fd0-344938afc7b2"
    }
    ```

1. _[Delay 30s-2m]_ Load filtered feed

    `POST /pro/v1/feeds/{user_uid}`
    ```
    {
        "feed_type_uuid": "00451d3e-1a4c-4dfe-9fd0-344938afc7b2",
        "filter_resolved": true
    }
    ```

1. _[Delay 30s-2m]_ User enters explore everything feed

    `POST /pro/v1/feeds/{user_uid}`
    ```
    {
        "feed_type_uuid": "74a60d87-b1b4-4346-86cf-2ec138fe018b"
    }
    ```

1. _[Delay 30s-2m]_ User updates topic feed subscriptions

    `POST /pro/v1/topics/{user_uid}`
    ```
    {
        "actions": [
            {
                "action": "unfollow",
                "feed_type_uuid": "d0cbd965-646f-4df7-aaf2-bbc4b69441f7"
            },
            {
                "action": "follow",
                "feed_type_uuid": "f67f55da-2823-49a1-be1a-f2e356c0903b"
            }
        ]
    }
    ```

1. _[Delay 20s]_ User enters topic feed

    `POST /pro/v1/feeds/{user_uid}`
    ```
    {
        "feed_type_uuid": "f67f55da-2823-49a1-be1a-f2e356c0903b"
    }
    ```

1. _[Delay 30s-2m]_ User scrolls down, loads next page in feed

    `POST /pro/v1/feeds/{user_uid}/update`
    ```
    {
        "feed_type_uuid": "f67f55da-2823-49a1-be1a-f2e356c0903b"
    }
    ```

1. _[Delay 20s-60s]_ User reacts to case.  

    `POST /pro/v1/case/{case_uuid}/reaction`
    ```
    {
        "user_uid": "{user_uid}", 
        "reaction": "agree", 
        "value": true
    }
    ```

1. Repeat #3 a 2-3 more times

1. _[Delay 30s-2m]_ User performs search

    `POST /pro/v1/search/cases`
    ```
    {
        "search_cursor": 0, 
        "search_index": ["74a60d87-b1b4-4346-86cf-2ec138fe018b"], 
        "search_term": "arm", 
        "search_user_uid": "{user_uid}"
    } 
    ```

1. _[Delay 20s-60s]_ User scrolls down, loads next page in search results

    `POST /pro/v1/search/cases`
    ```
    {
        "search_cursor": 20, 
        "search_index": ["74a60d87-b1b4-4346-86cf-2ec138fe018b"], 
        "search_term": "arm", 
        "search_user_uid": "{user_uid}"
    } 
    ```

1. _[Delay 20s-60s]_ User enters CME center

    `GET /pro/v1/cme/activities/{user_uid}`
    ```
    No Body
    ```

## Comment posting

1. User enters case detail, reads comments, leaves a new comment

    `POST /pro/v1/comment/{case_uuid}`
    ```
    {
        "user_uid": "{user_uid}", 
        "comment_text": "New comment", 
        "parent_comment_uuid": null
    } 
    ```

1. _[Delay 1m-3m]_ Post a reply to another comment

    `POST /pro/v1/comment/{case_uuid}`
    ```
    {
        "user_uid": "{user_uid}", 
        "comment_text": "New comment", 
        "parent_comment_uuid": {comment_uuid}
    } 
    ```


## Case Upload:

1. Upload case image
    
    `POST /pro/v1/draft/{user_uid}/{draft_uid}/media`
    ```
    Accepts multipart form data with the field name 'picture'
    ```
   After submitting this request, the API updates firestore (`/userDraftsDB/{user_uuid}/all/{draft_id}/media`) with the data to submit during case upload

1. _[Delay 5m]_ Upload case
    
    `POST /pro/v1/draft/{user_uid}/{draft_uid}?state=submit`
    ```
    {
        "caption": "Case details",
        "case_uuid": null,
        "label_uuids": [
            "51cc9c97-1966-4d0a-8715-0f9234be0f2e",
            "ac7dbc06-3633-4b97-bb31-3f5d431be326"
        ],
        "media": [
            {
                "filename": "88df5e3cce70f2543b17765ff02c5f5c66fba878cb9142cd855209d516e8e354.png",
                "height": 5100,
                "index": 0,
                "original_filename": "88df5e3cce70f2543b17765ff02c5f5c66fba878cb9142cd855209d516e8e3540",
                "type": "image",
                "upload_completed": true,
                "url": "https://figure1-pro-dev.imgix.net/cases/images/88df5e3cce70f2543b17765ff02c5f5c66fba878cb9142cd855209d516e8e354.png",
                "width": 3400
            }
        ],
        "paging": false,
        "specialty_uuids": [
            "84fb3894-fb28-45ae-8ff7-ef34f2f96a4f",
            "8b951b46-cfae-4a7d-8912-e7ed4bb9904e"
        ],
        "title": "Case title"
    }
    ```
   
 ## Case Moderation:
 
1. Moderator approves case

    `POST /admin/v1/moderation/cases/{case_uuid}/approve`
    ```
    {
        "moderator_uid": "{user_uid}"
    }
    ```
 
2. _[Delay 60s]_ Tagger submits case specialties

    `POST /admin/v1/moderation/tagging/{case_uuid}/specialties`
    ```
    {
       "set": [
           "acd94024-dacc-4e9a-a0e2-5c08d477fd81",
            "e42f6078-c0b9-4f3e-bd6a-f6eeff333f63"
       ]
    }
    ```
3. _[Delay 60s]_ Tagger submits new mesh terms

    `POST /admin/v1/moderation/tagging/{case_uuid}/mesh`
    ```
    {
       "set": ["Arm", "Arm Injuries"]
    }
    ```
   
4. _[Delay 30s]_ Tagger approves mesh terms

    `POST /admin/v1/moderation/tagging/{case_uuid}/mesh/approve`
    ```
    {
        "moderator_uid": "{user_uid}"
    }
   ```


## User Creation / Onboarding:

1. Check email availability

    `GET /pro/v1/user/validate/email/{email_address}`
    ```
    No Body
    ```

1. _[Delay 20s]_ Create account

    `POST /pro/v1/user/create`
    ```
    {
        "email": "{email_address}",
        "first_name": "Test",
        "last_name": "User",
        "profession_tree_uuid": "e0911f79-16df-4adb-bd92-b3dffa289460",
        "profession_uuid": "e0911f79-16df-4adb-bd92-b3dffa289460",
        "screen_id": "registrationStarted",
        "user_uid": "test_user_uuid_123"
    }
    ```

1. _[Delay 1m-3m]_ Submit Verification

    `POST /pro/v1/verification`
    ```
    {
        "method": "license",
        "license_number": "12345",
        "user_uid": "test_user_uuid_123",
        "graduation_year": 2015,
        "license_country_code": "0137a074-9139-4187-878b-15a5af6f98ae",
        "license_school_code": "76a7911e-e1b1-474e-9914-245587217ecf",
        "license_state_code": "d826ddd1-643c-4c33-b7c7-82d73dede7a6"
    }
    ```

1. _[Delay 1-2m]_ Check username availability

    `GET /pro/v1/user/validate/username/{username}`
    ```
    No Body
    ```

1. _[Delay 30s]_ Update user details

    `POST /pro/v1/user/{user_uid}`
    ```
    {
        "username": "TestUser",
        "interests": [
            "6c47efa1-1ecd-44d7-8859-71c5a6baad6e",
            "851a6d0a-f660-4921-9cd8-fb44853ee38b"
        ],
        "primarySpecialty": "378da919-1478-438f-89bb-335582785293",
        "screen_id": "registrationUsername"
    }
    ```

1. _[Delay 30s]_ Follow topic

    `POST /pro/v1/topic/{user_uid}`
    ```
    {
      "action": "follow",
      "feed_type_uuid": "d0cbd965-646f-4df7-aaf2-bbc4b69441f7"
    }
    ```

1. _[Delay 10s]_ Follow another topic

    `POST /pro/v1/topic/{user_uid}`
    ```
    {
      "action": "follow",
      "feed_type_uuid": "aca8ded1-9b49-4870-bd81-83c62cabed09"
    }
   ```

1. _[Delay 10s]_ Follow another topic

    `POST /pro/v1/topic/{user_uid}`
    ```
    {
      "action": "follow",
      "feed_type_uuid": "53158022-29ea-44ea-b2bf-303a9416e724"
    }
   ```

1. _[Delay 20s]_ Mark onboarding completed

    `POST /pro/v1/user/{user_uid}`
    ```
    {
        "onboardingCompleted": true
    }
    ```
