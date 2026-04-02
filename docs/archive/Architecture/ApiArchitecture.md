# API Architecture

## Endpoint Patterns

Endpoints under `/pro/v1` typically follow these patterns:
 
 1.  Heavy operations are not handled synchronously.  Instead, a response is returned quickly (typically a 202) with the 
 task id of a celery task which is invoked to run asynchronously. 
 
 2.  Response data is written to firestore instead of being provided in a response body.  
 
     For example, a call to `GET /pro/v1/case` returns a simple success message in the response body.  The case data can 
     then be read from firestore at `/casesDBv2/{case_uuid}`
     

## Firestore Overview
 
### Reference Data

This firestore collections holds static data and uuids that are needed for various aspects of the API.  For example,
when loading a feed a `feed_type_uuid` is required which can be found within the `/referenceData/feeds` document.

Reference Data is updated by the backend and should not be modified otherwise.
