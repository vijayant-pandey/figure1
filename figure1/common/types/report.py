import enum


class ReportReason(enum.Enum):
    OTHER = 'other'
    DISRESPECTFUL = 'disrespectful'
    PRIVACY = 'privacy'
    LACK_EVIDENCE = 'lack_evidence'
    PROMOTIONAL = 'promotional'
    OFF_TOPIC = 'off_topic'
