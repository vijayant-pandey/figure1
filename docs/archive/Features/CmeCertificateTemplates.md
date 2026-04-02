# CME Certificate Templates

## Overview

CME certificates are rendered from certificate templates in a docx format.  On render the template values are inflated,
a pdf is generated and then uploaded to s3.

This document describes some details on template generation and usage.

## CME Activities

Activity certificate templates are targeted based on a user's profession.  Each CME activity is associated with 0 or 
more certificate templates.  The templates for a CME activity do not need to exhaust all possible professions.

All users can complete CME activities regardless of if a template is available.  When a user completes a CME activity 
if there is a matching template for their profession a certificate is rendered.  If there is no match they do not
receive a certificate to download.

Activity certificate templates are handled by BD and uploaded directly from the admin tool.  

## Case CME

At the time of writing only a single template is required for case CME.  This differs from activity CME mainly because
only physicians have access to case CME.  Because there is a single template, the data for which template to use isn't
stored in a db table and is instead just in an AppSettings value `case_cme_template`.

The template used for case CME comes from [this google doc](https://docs.google.com/document/d/1LfICt5IOYv0A4SoTEvwUnDEbG_9i4JNC/edit?usp=sharing&ouid=103528368610364903031&rtpof=true&sd=true).
If modifications are required it can be updated, exported as a docx and uploaded to s3.
