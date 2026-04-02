class CampaignMapSchema:
    campaign_map_data = {
        "mappings": {
            "properties": {
                "createdAt": {
                    "type": "date",
                    "format": "yyyy-MM-dd HH:mm:ss.SSSSSSXXX||yyyy-MM-dd HH:mm:ssXXX||date_optional_time"
                },
                "updatedAt": {
                    "type": "date",
                    "format": "yyyy-MM-dd HH:mm:ss.SSSSSSXXX||yyyy-MM-dd HH:mm:ssXXX||date_optional_time"
                },
                "campaignUuid": {
                    "type": "keyword"
                },
                "authorUuid": {
                    "type": "keyword"
                },
                "authorName": {
                    "type": "text"
                },
                "name": {
                    "type": "text"
                },
                "clientName": {
                    "type": "text"
                },
                "state": {
                    "type": "keyword"
                },
                "archivedAt": {
                    "type": "date",
                    "format": "yyyy-MM-dd HH:mm:ss.SSSSSSXXX||yyyy-MM-dd HH:mm:ssXXX||date_optional_time"
                },
                "archivedByUuid": {
                    "type": "keyword"
                },
                "archivedByName": {
                    "type": "text"
                },
                "campaignPriority": {
                    "type": "integer"
                },
                "isSponsored": {
                    "type": "boolean"
                },
                "cases": {
                    "type": "nested",
                    "properties": {
                        "caseUuid": {
                            "type": "keyword"
                        },
                        "startDate": {
                            "type": "date",
                            "format": "yyyy-MM-dd HH:mm:ss.SSSSSSXXX||yyyy-MM-dd HH:mm:ssXXX||date_optional_time"
                        },
                        "endDate": {
                            "type": "date",
                            "format": "yyyy-MM-dd HH:mm:ss.SSSSSSXXX||yyyy-MM-dd HH:mm:ssXXX||date_optional_time"
                        },
                        "tacticPriority": {
                            "type": "integer"
                        },
                        "caseState": {
                            "type": "keyword"
                        },
                        "name": {
                            "type": "text"
                        },
                        "isSponsored": {
                            "type": "boolean"
                        },
                    }
                },
                "targetCountries": {
                    "type": "nested",
                    "properties": {
                        "countryUuid": {
                            "type": "keyword"
                        },
                        "countryName": {
                            "type": "keyword"
                        },
                        "path": {
                            "type": "keyword"
                        },
                        "depth": {
                            "type": "keyword"
                        }
                    }
                },
                "targetSpecialties": {
                    "type": "nested",
                    "properties": {
                        "treeUuid": {
                            "type": "keyword"
                        }
                    }
                },
                "targetLanguages": {
                    "type": "nested",
                    "properties": {
                        "language": {
                            "type": "keyword"
                        }
                    }
                },
                "targetVerification": {
                    "type": "boolean"
                },
                "previewUsers": {
                    "type": "nested",
                    "properties": {
                        "userUid": {
                            "type": "keyword"
                        },
                        "userUuid": {
                            "type": "keyword"
                        },
                        "username": {
                            "type": "text"
                        }
                    }
                }
            }
        }
    }
