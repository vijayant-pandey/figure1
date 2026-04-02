## Onboarding Workflow

### Summary

State management of how users progress through onboarding is handled by the backend.  The current state that a user has 
reached is represented within `UserState.onboarding_state`

Progression through states is handled by checking if the user has submitted the required data to move to the next state.  
Each state class defines what data is required for progression, and this should align with what frontend clients ask for 
in the corresponding screen(s).

### Updating State

At the time of writing there are four endpoints that are used for progression through onboarding:
 - Create user:  `/pro/v1/user/create`
 - Update user:  `/pro/v1/user/{user_uid}`
 - Set legacy user UID:  `/pro/v1/user/legacy/set_user_uid`
 - Submit verification:  `/pro/v1/verification`

Each of these endpoints handles updating `UserState.onboarding_state` synchronously, based on the latest state of the 
user who is onboarding.  This updated state is written to the db, synced to firestore, and returned in the response 
object for the endpoint.  The clients rely on the response object in order to determine which screen to transition to 
next.

### Onboarding Flowcharts

The following flowcharts show how the `OnboardingState` values map to screens in the onboarding flow.  

Mobile:
https://lucid.app/lucidchart/16563aea-d568-47d4-adc3-ab17d746b1e3/edit?invitationId=inv_ded84d3b-eda2-4297-80e3-3c4855a051ca
Web:
https://lucid.app/lucidchart/8ce89fd7-8c42-44b5-a684-9459e267ac5d/edit?invitationId=inv_f5dd2b32-6a75-4f1a-96dd-0237ee5ed590

