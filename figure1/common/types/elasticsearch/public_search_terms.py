import logging
from elasticsearch_dsl import Document, Completion, Keyword, Search
from elasticsearch.helpers import bulk

logger = logging.getLogger('figure1.pro.public_search_terms_v2')


class CompletionIndex(Document):
    searchCompletion = Completion(contexts=[dict(name='search_type', type='category', path='searchCategory')])
    searchCategory = Keyword(multi=True)
    userUuid = Keyword()
    specialtyTreeUuid = Keyword()
    specialtyUuid = Keyword()

    def add_mesh_term_completion(self, meshTerms, meshCategory=None):
        self.searchCompletion = meshTerms
        if meshCategory:
            self.searchCategory = [meshCategory, 'mesh']
        else:
            self.searchCategory = 'mesh'
        return self

    def add_specialty_tree_completion(self, treeUuid, onboardingDisplayName):
        self.searchCompletion = onboardingDisplayName
        self.specialtyTreeUuid = treeUuid
        self.searchCategory = 'specialtyTree'
        return self

    def add_specialty_completion(self, specialtyUuid, specialtyName):
        self.searchCompletion = specialtyName
        self.searchCategory = 'specialty'
        self.specialtyUuid = specialtyUuid
        return self

    def add_user_completion(self,
                            user_uuid,
                            username=None,
                            display_name=None):
        self.searchCompletion = []
        if username is not None:
            self.searchCompletion.append(username)
        if display_name is not None:
            self.searchCompletion.append(display_name)
        self.searchCategory = 'user'
        self.userUuid = user_uuid
        return self


def _bulk_reindex_mesh_terms(es):
    mesh_terms = set()
    mesh_term_search = Search(index='newcases', using=es).query("match_all")
    mesh_term_search = mesh_term_search.filter('terms', caseState=['APPROVED'])
    mesh_term_search = mesh_term_search.source(['meshTerms'])
    logger.error("Searching for mesh terms")
    for hit in mesh_term_search.scan():
        if not hasattr(hit, 'meshTerms'):
            continue
        for mt in hit.meshTerms:
            mesh_terms.add(mt)
    for unique_mesh_term in mesh_terms:
        idx = CompletionIndex()
        idx.searchCompletion = unique_mesh_term
        idx.searchCategory = ["mesh"]
        yield idx.to_dict(include_meta=True)


def reindex_mesh_terms(es):
    logger.error("Deleting existing mesh terms completion")
    CompletionIndex.search() \
        .query("term", searchCategory='mesh') \
        .params(wait_for_completion=True) \
        .delete()
    logger.error("Mesh terms deleted")
    if not es.indices.exists_alias(name='newcases'):
        return
    logger.error("Starting mesh term update")
    bulk(es, actions=_bulk_reindex_mesh_terms(es=es))


def _bulk_reindex_user_terms(es):
    user_search = Search(index='users', using=es) \
        .query("match_all").exclude('term', userHiddenFromSearch=True) \
        .source(['username', 'displayName', 'userUuid'])
    logger.error("User Search %s", user_search.to_dict())
    for hit in user_search.scan():
        user = CompletionIndex(userUuid=hit.userUuid)
        completion = []
        if hasattr(hit, 'username'):
            completion.append(hit.username)
        if hasattr(hit, 'displayName'):
            completion.append(hit.displayName)
        if completion:
            user.searchCompletion = completion
            user.searchCategory = ["user"]
            yield user.to_dict(include_meta=True)
        else:
            continue


def reindex_user_terms(es):
    logger.error("Delete existing user search terms")
    CompletionIndex.search() \
        .query("term", searchCategory='user') \
        .params(wait_for_completion=True) \
        .delete()
    logger.error("Delete complete, starting bulk insert")
    if not es.indices.exists_alias(name='users'):
        return
    bulk(client=es, actions=_bulk_reindex_user_terms(es=es))
    logger.error("User search term update complete")
