# External Email Subscriptions

## Overview

The external email subscription API was created as a way for users to subscribe to figure 1 mailing lists from the 
marketing site.  Instead of updating iterable directly the marketing site would make a request to the backend where
the subscriptions would be proxied to iterable and the postgres db would be updated.

Unlike most other endpoints this functionality is available for emails not registered in `u_user`.  On subscription
if the email exists in `u_user` a normal update to `u_user_communication_preferences` is followed.  If the email does 
not exist the subscription is instead recorded in `u_anonymous_email_subscriber`.  If these anonymous email subscribers
subsequently sign up for a figure 1 account their previous preferences are read from iterable during onboarding and
maintained.

## Current state

The API to allow external email subscriptions was mostly completed (see `figure1.pro.api` package).   A page was drafted 
on the marketing site which exposed a way to subscribe to differentials and the ddx newsletter.  However this there one 
outstanding issue that prevented rolling it out and as a result the feature is not live.

The issue is that our iterable message types defined as opt-out and thus are subscribed by default.  The API endpoint 
worked by initializing preferences for all of the messages types that the backend is aware of; however message types 
that are not defined in `r_communication_settings` were not sent a value in the iterable request and therefore remain 
subscribed. Furthermore new message types in iterable would be enabled for these users.  This is an issue for marketing 
site subscribers since the expectation was that they would only be subscribed to the ones they explicitly chose.  

Around the time I realized this issue the priorities had shifted and there was no longer immediate demand for the
marketing site email subscription to exist, thus this never got fixed.  The likely solution would be to change our
iterable message types to opt-in.  This requires an iterable CSR to enable the feature and has a documented
[breaking change](https://support.iterable.com/hc/en-us/articles/204780529-Message-Channels-and-Message-Types-Overview-#breaking-api-change) 
associated with it that should be checked first.


