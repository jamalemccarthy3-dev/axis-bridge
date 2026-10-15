#ifndef RESEARCH_ENGINE_H
#define RESEARCH_ENGINE_H

#define RESEARCH_MAX_DOCS 64
#define RESEARCH_DOC_CHARS 1024

/* The Research Engine: a small local search over documents it has been given. It needs no network and no portal.
   Scoring: each word of the query (letters and digits, case ignored) counts once per occurrence in the document, and a document's own id counts too. */
void research_init(void);                                         /* empties the index */
int research_add(const char *doc_id, const char *text);           /* 1 added or replaced, 0 if id/text is empty or the index is full; long text is cut */
int research_count(void);

typedef struct {
    char doc_id[48];
    int score;
} ResearchHit;

/* Fills hits (best first, ties by insertion order) with up to max_hits documents whose score is above zero; returns how many. */
int research_search(const char *query_string, ResearchHit *hits, int max_hits);
/* Prints the hits for a query. */
void research_query(const char* query_string);

#endif
