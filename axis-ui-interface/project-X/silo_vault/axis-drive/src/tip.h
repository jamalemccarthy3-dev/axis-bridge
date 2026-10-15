
#ifndef TIP_H
#define TIP_H

/* The TIP maintains the permanent audit ledger: one line per event, "[unix time] TIP RECORD: message", appended to the file named by AXIS_TIP_LOG
   (default build_history.log in the current folder). Returns 1 if the line was written, 0 if the file could not be opened or the message is empty. */
int log_build_event(const char *message);

#endif
