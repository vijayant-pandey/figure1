import pytest
from figure1.common.types import MeshModel, MeshConceptModel, MeshTermsModel
from figure1.common.types.mesh_api import MeshNote
from figure1.admin.moderation.tagging.mesh_on_demand import MeshDataAPI

mesh_json_test = {
    "@id": "http://id.nlm.nih.gov/mesh/D006323",
    "@type": "http://id.nlm.nih.gov/mesh/vocab#TopicalDescriptor",
    "http://id.nlm.nih.gov/mesh/vocab#active": True,
    "allowableQualifier": ["http://id.nlm.nih.gov/mesh/Q000517", "http://id.nlm.nih.gov/mesh/Q000097",
                           "http://id.nlm.nih.gov/mesh/Q000196", "http://id.nlm.nih.gov/mesh/Q000382",
                           "http://id.nlm.nih.gov/mesh/Q000601", "http://id.nlm.nih.gov/mesh/Q000235",
                           "http://id.nlm.nih.gov/mesh/Q000188", "http://id.nlm.nih.gov/mesh/Q000150",
                           "http://id.nlm.nih.gov/mesh/Q000523", "http://id.nlm.nih.gov/mesh/Q000145",
                           "http://id.nlm.nih.gov/mesh/Q000534", "http://id.nlm.nih.gov/mesh/Q000662",
                           "http://id.nlm.nih.gov/mesh/Q000134", "http://id.nlm.nih.gov/mesh/Q000628",
                           "http://id.nlm.nih.gov/mesh/Q000503", "http://id.nlm.nih.gov/mesh/Q000473",
                           "http://id.nlm.nih.gov/mesh/Q000201", "http://id.nlm.nih.gov/mesh/Q000378",
                           "http://id.nlm.nih.gov/mesh/Q000401", "http://id.nlm.nih.gov/mesh/Q000276",
                           "http://id.nlm.nih.gov/mesh/Q000208", "http://id.nlm.nih.gov/mesh/Q000151",
                           "http://id.nlm.nih.gov/mesh/Q000191", "http://id.nlm.nih.gov/mesh/Q000453",
                           "http://id.nlm.nih.gov/mesh/Q000178", "http://id.nlm.nih.gov/mesh/Q000175",
                           "http://id.nlm.nih.gov/mesh/Q000532", "http://id.nlm.nih.gov/mesh/Q000266",
                           "http://id.nlm.nih.gov/mesh/Q000469", "http://id.nlm.nih.gov/mesh/Q000139",
                           "http://id.nlm.nih.gov/mesh/Q000209", "http://id.nlm.nih.gov/mesh/Q000652",
                           "http://id.nlm.nih.gov/mesh/Q000451", "http://id.nlm.nih.gov/mesh/Q000000981",
                           "http://id.nlm.nih.gov/mesh/Q000821"],
    "annotation": {
        "@language": "en",
        "@value": "do not confuse with CARDIAC ARREST, SUDDEN see DEATH, SUDDEN, CARDIAC"
    },
    "broaderDescriptor": "http://id.nlm.nih.gov/mesh/D006331",
    "concept": "http://id.nlm.nih.gov/mesh/M0009939",
    "dateCreated": "1999-01-01",
    "dateEstablished": "1960-01-01",
    "dateRevised": "2007-07-09",
    "historyNote": {
        "@language": "en",
        "@value": "ASYSTOLE was see under ARRHYTHMIA 1969-90"
    },
    "identifier": "D006323",
    "nlmClassificationNumber": "WG 214",
    "onlineNote": {
        "@language": "en",
        "@value": "use HEART ARREST to search ASYSTOLE 1969-74"
    },
    "preferredConcept": "http://id.nlm.nih.gov/mesh/M0009938",
    "preferredTerm": "http://id.nlm.nih.gov/mesh/T019156",
    "publicMeSHNote": {
        "@language": "en",
        "@value": "ASYSTOLE was see under ARRHYTHMIA 1969-90"
    },
    "seeAlso": ["http://id.nlm.nih.gov/mesh/D006324", "http://id.nlm.nih.gov/mesh/D016887"],
    "treeNumber": "http://id.nlm.nih.gov/mesh/C14.280.383",
    "label": {
        "@language": "en",
        "@value": "Heart Arrest"
    },
    "@context": {
        "concept": {
            "@id": "http://id.nlm.nih.gov/mesh/vocab#concept",
            "@type": "@id"
        },
        "seeAlso": {
            "@id": "http://id.nlm.nih.gov/mesh/vocab#seeAlso",
            "@type": "@id"
        },
        "allowableQualifier": {
            "@id": "http://id.nlm.nih.gov/mesh/vocab#allowableQualifier",
            "@type": "@id"
        },
        "preferredConcept": {
            "@id": "http://id.nlm.nih.gov/mesh/vocab#preferredConcept",
            "@type": "@id"
        },
        "nlmClassificationNumber": {
            "@id": "http://id.nlm.nih.gov/mesh/vocab#nlmClassificationNumber"
        },
        "broaderDescriptor": {
            "@id": "http://id.nlm.nih.gov/mesh/vocab#broaderDescriptor",
            "@type": "@id"
        },
        "publicMeSHNote": {
            "@id": "http://id.nlm.nih.gov/mesh/vocab#publicMeSHNote"
        },
        "onlineNote": {
            "@id": "http://id.nlm.nih.gov/mesh/vocab#onlineNote"
        },
        "dateEstablished": {
            "@id": "http://id.nlm.nih.gov/mesh/vocab#dateEstablished",
            "@type": "http://www.w3.org/2001/XMLSchema#date"
        },
        "annotation": {
            "@id": "http://id.nlm.nih.gov/mesh/vocab#annotation"
        },
        "treeNumber": {
            "@id": "http://id.nlm.nih.gov/mesh/vocab#treeNumber",
            "@type": "@id"
        },
        "label": {
            "@id": "http://www.w3.org/2000/01/rdf-schema#label"
        },
        "preferredTerm": {
            "@id": "http://id.nlm.nih.gov/mesh/vocab#preferredTerm",
            "@type": "@id"
        },
        "dateCreated": {
            "@id": "http://id.nlm.nih.gov/mesh/vocab#dateCreated",
            "@type": "http://www.w3.org/2001/XMLSchema#date"
        },
        "dateRevised": {
            "@id": "http://id.nlm.nih.gov/mesh/vocab#dateRevised",
            "@type": "http://www.w3.org/2001/XMLSchema#date"
        },
        "historyNote": {
            "@id": "http://id.nlm.nih.gov/mesh/vocab#historyNote"
        },
        "active": {
            "@id": "http://id.nlm.nih.gov/mesh/vocab#active",
            "@type": "http://www.w3.org/2001/XMLSchema#boolean"
        },
        "identifier": {
            "@id": "http://id.nlm.nih.gov/mesh/vocab#identifier"
        }
    }
}

mesh_concept_json = {
    "@id": "http://id.nlm.nih.gov/mesh/M0009938",
    "@type": "http://id.nlm.nih.gov/mesh/vocab#Concept",
    "http://id.nlm.nih.gov/mesh/vocab#active": True,
    "broaderConcept": "http://id.nlm.nih.gov/mesh/M0009939",
    "identifier": "M0009938",
    "preferredTerm": "http://id.nlm.nih.gov/mesh/T019156",
    "scopeNote": {
        "@language": "en",
        "@value": "Cessation of heart beat or MYOCARDIAL CONTRACTION. If it is treated within a few minutes,"
                  " heart arrest can be reversed in most cases to normal cardiac rhythm and effective circulation."
    },
    "term": ["http://id.nlm.nih.gov/mesh/T019155", "http://id.nlm.nih.gov/mesh/T019154"],
    "label": {
        "@language": "en",
        "@value": "Heart Arrest"
    },
    "@context": {
        "term": {
            "@id": "http://id.nlm.nih.gov/mesh/vocab#term",
            "@type": "@id"
        },
        "identifier": {
            "@id": "http://id.nlm.nih.gov/mesh/vocab#identifier"
        },
        "active": {
            "@id": "http://id.nlm.nih.gov/mesh/vocab#active",
            "@type": "http://www.w3.org/2001/XMLSchema#boolean"
        },
        "broaderConcept": {
            "@id": "http://id.nlm.nih.gov/mesh/vocab#broaderConcept",
            "@type": "@id"
        },
        "label": {
            "@id": "http://www.w3.org/2000/01/rdf-schema#label"
        },
        "scopeNote": {
            "@id": "http://id.nlm.nih.gov/mesh/vocab#scopeNote"
        },
        "preferredTerm": {
            "@id": "http://id.nlm.nih.gov/mesh/vocab#preferredTerm",
            "@type": "@id"
        }
    }
}

mesh_term_json = {
    "@id": "http://id.nlm.nih.gov/mesh/T019157",
    "@type": "http://id.nlm.nih.gov/mesh/vocab#Term",
    "http://id.nlm.nih.gov/mesh/vocab#active": True,
    "altLabel": {
        "@language": "en",
        "@value": "Arrest, Cardiopulmonary"
    },
    "dateCreated": "1977-04-27",
    "identifier": "T019157",
    "lexicalTag": {
        "@language": "en",
        "@value": "NON"
    },
    "prefLabel": {
        "@language": "en",
        "@value": "Cardiopulmonary Arrest"
    },
    "thesaurusID": {
        "@language": "en",
        "@value": "UNK (19XX)"
    },
    "@context": {
        "lexicalTag": {
            "@id": "http://id.nlm.nih.gov/mesh/vocab#lexicalTag"
        },
        "dateCreated": {
            "@id": "http://id.nlm.nih.gov/mesh/vocab#dateCreated",
            "@type": "http://www.w3.org/2001/XMLSchema#date"
        },
        "active": {
            "@id": "http://id.nlm.nih.gov/mesh/vocab#active",
            "@type": "http://www.w3.org/2001/XMLSchema#boolean"
        },
        "prefLabel": {
            "@id": "http://id.nlm.nih.gov/mesh/vocab#prefLabel"
        },
        "thesaurusID": {
            "@id": "http://id.nlm.nih.gov/mesh/vocab#thesaurusID"
        },
        "identifier": {
            "@id": "http://id.nlm.nih.gov/mesh/vocab#identifier"
        },
        "altLabel": {
            "@id": "http://id.nlm.nih.gov/mesh/vocab#altLabel"
        }
    }
}


@pytest.fixture(scope='session')
def mesh_term_data():
    return mesh_term_json


@pytest.fixture(scope='session')
def mesh_concept_data():
    return mesh_concept_json


@pytest.fixture(scope='session')
def mesh_data():
    return mesh_json_test


def test_mesh_model(mesh_data):
    m = MeshModel.parse_obj(mesh_data)
    assert m.preferredTerm == 'T019156'
    assert m.preferredConcept == 'M0009938'
    assert isinstance(m.label, MeshNote)


def test_mesh_concept_model(mesh_concept_data):
    concept = MeshConceptModel.parse_obj(mesh_concept_data)
    assert concept.preferredTerm == 'T019156'
    assert 'T019155' in concept.terms
    assert isinstance(concept.scopeNote, MeshNote)


def test_mesh_terms_model(mesh_term_data):
    term = MeshTermsModel.parse_obj(mesh_term_data)
    assert isinstance(term.preferredLabel, MeshNote)
    assert isinstance(term.alternateLabel, MeshNote)


def test_search():
    label = MeshDataAPI.fix_alternate_label('Arrest, Cardiac')
    assert label == 'Cardiac Arrest'
