## Institutional Profiles

Institutional and/or sponsored profiles primarily take the form of a profile which prominently shows the name of the institution or sponsor in the profile. This would normally be used to post content that showcases the specialty of the institution or something along those lines.


##### Notes on Users/User Profiles

There is a difference between Users and User Profiles that is important to understand. Every user that is able to log in has a profile, what differentiates the profile from the user is the ability to log in. The user will have an auth record in firestore.

A profile on the other hand, contains the same fields as a user but is unable to log in. There is no entry in the users table for a profile. 

Abstracting these two concepts allows for profiles that are far more flexible than profiles that remain tied to a single user. For example, one could allow any user to publish on behalf of a profile. This could be used to allow all users at one hospital to publish cases under the hospital’s profile.


### Security Considerations

The key concern for institutions who have profiles is likely to be that of reputation. Posting inappropriate content as the institution would substantially harm their reputation among those they are targeting.

To guard against this, there are two measures built into this feature:



1. There is no shared login - it is not possible to log in as the institution, all content posted on behalf of the institution. This enables accountability for all posted content.
2. All posted content goes through moderation and tagging. This ensures that someone external to the institution reviews the content before it is posted. 


### Profile Constraints

The profile itself on the backend does not have to be substantially different from a standard profile, however there would be no authentication information associated with it. The profile would need to be created by a moderator. 


### Posting Content

For a user to make a change to a profile, the user would have an attribute that indicates they are able to post on behalf of a certain profile. In this way, every user is accountable for posts that are made, but the poster would be shown as the institutional profile.

In the event that a user is removed from having the ability to edit, the posts created would not be affected since the author would be shown as that institutional profile.

Note that any posts on behalf of an institutional profile would not appear in the user’s feed. 


#### Drafts

In many cases, it may be desirable to have another user review a case before it is submitted for moderation. If a user chooses to post on behalf of another profile before they start working on the draft, then the draft could be saved under the profile that the user is posting as. This is a significant amount of work however, on both the frontend and backend that would need to be scoped out.


### User Access

For profiles like this, we would not support fine-grained access. It does not seem like something that would be used much and it would add significant complication. As a stopgap though, we could allow a user to only post cases or only post comments or post both.


### Moderation

Since this content comes from outside of Figure1, it still goes through moderation, however it would go through the Partner Cases moderation queue which gives it a higher priority. After this, it would go through the tagging flow as well.


### Changes Required

 Backend:



*   Add a flag to the users metadata that allows posting on behalf of a specific uuid
*   Accept a flag when drafting or uploading a case content that says which user it is posting on behalf of. As a security measure - we should take the user_uid passed in and ensure it can post on behalf of the uuid it asks for.
*   Same as above, but for comments
*   Add a flag to user profile information saying they can post on behalf of a specific uuid. If this flag does not exist, the user may not post on behalf of anyone.
*   Add an endpoint to create an institutional profile, this should be in the /admin/ section.
*   Add an endpoint that allows a given user to post on behalf of a specific institution. 

Frontend:



*   If a flag allowing a user to post on behalf of another uuid exists, show something - maybe a dropdown? - to select who to post on behalf of, the default would be the user themselves. For cases specifically, we should think about how to do drafts. 
*   Same as above for comments


## Institutional Groups

Groups by institution are out of scope at the moment.
