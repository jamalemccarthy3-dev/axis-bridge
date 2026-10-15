#include "research_engine.h"
#include <ctype.h>
#include <stdio.h>
#include <string.h>

static struct { char id[48]; char text[RESEARCH_DOC_CHARS]; } docs[RESEARCH_MAX_DOCS];
static int doc_count = 0;

void research_init(void) { doc_count = 0; }
int research_count(void) { return doc_count; }

int research_add(const char *doc_id, const char *text) {
    int i, slot = -1;
    char id[48];
    if (doc_id == NULL || text == NULL || doc_id[0] == '\0' || text[0] == '\0') return 0;
    snprintf(id, sizeof id, "%s", doc_id);
    for (i = 0; i < doc_count; i++) if (strcmp(docs[i].id, id) == 0) slot = i;
    if (slot < 0) {
        if (doc_count == RESEARCH_MAX_DOCS) return 0;
        slot = doc_count++;
    }
    memcpy(docs[slot].id, id, sizeof id);
    snprintf(docs[slot].text, sizeof docs[slot].text, "%s", text);
    return 1;
}

/* the next word of s (letters and digits, lower-cased) into w; returns the position after it, or NULL when there are no more */
static const char *next_word(const char *s, char *w, size_t cap) {
    size_t n = 0;
    while (*s && !isalnum((unsigned char)*s)) s++;
    if (!*s) return NULL;
    while (*s && isalnum((unsigned char)*s)) {
        if (n + 1 < cap) w[n++] = (char)tolower((unsigned char)*s);
        s++;
    }
    w[n] = '\0';
    return s;
}

static int count_word(const char *text, const char *word) {
    char w[64];
    int hits = 0;
    const char *p = text;
    while ((p = next_word(p, w, sizeof w)) != NULL) if (strcmp(w, word) == 0) hits++;
    return hits;
}

int research_search(const char *query_string, ResearchHit *hits, int max_hits) {
    int scores[RESEARCH_MAX_DOCS], order[RESEARCH_MAX_DOCS], n = 0, i, j, out = 0;
    char w[64];
    const char *q = query_string;
    if (query_string == NULL || hits == NULL || max_hits <= 0) return 0;
    for (i = 0; i < doc_count; i++) scores[i] = 0;
    while ((q = next_word(q, w, sizeof w)) != NULL)
        for (i = 0; i < doc_count; i++) scores[i] += count_word(docs[i].text, w) + count_word(docs[i].id, w);
    for (i = 0; i < doc_count; i++) if (scores[i] > 0) order[n++] = i;
    for (i = 1; i < n; i++) {                            /* stable insertion sort, best first */
        int k = order[i];
        for (j = i - 1; j >= 0 && scores[order[j]] < scores[k]; j--) order[j + 1] = order[j];
        order[j + 1] = k;
    }
    for (i = 0; i < n && out < max_hits; i++, out++) {
        snprintf(hits[out].doc_id, sizeof hits[out].doc_id, "%s", docs[order[i]].id);
        hits[out].score = scores[order[i]];
    }
    return out;
}

void research_query(const char* query_string) {
    ResearchHit hits[5];
    int n, i;
    printf("Researching: %s\n", query_string ? query_string : "");
    n = research_search(query_string, hits, 5);
    if (n == 0) printf("  no match in %d document(s)\n", doc_count);
    for (i = 0; i < n; i++) printf("  %d. %s (score %d)\n", i + 1, hits[i].doc_id, hits[i].score);
}
