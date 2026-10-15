# main.py
import logging
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.join(HERE, "lib"), os.path.join(HERE, "src", "governor", "lib")):
    if _p not in sys.path:
        sys.path.append(_p)

from cleaner_sanitizer_tool import CleanerSanitizerTool
from vocabulary_mapping_utility_tool import VocabularyMappingTool
from tokenizer_utility_tool import tokenizerutilitytool as TokenizerTool
from embedding_vectorizer_utility_tool import EmbeddingVectorizerTool as EmbeddedVectorizerTool
from governor_alignment_utility_tool import governoralignmenttool as GovernorAlignmentTool
from performance_monitor_tool import PerformanceMonitorTool
from checkpoint_state_manager_tool import CheckpointStateManagerTool

# Configure logging for the entire factory
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.FileHandler(os.path.join(HERE, "factory_main.log")), logging.StreamHandler()]
)

class FactoryOrchestrator:
    def __init__(self):
        self.logger = logging.getLogger("Factory.Orchestrator")
        self.sanitizer = CleanerSanitizerTool()
        self.mapper = VocabularyMappingTool()
        self.tokenizer = TokenizerTool()
        self.vectorizer = EmbeddedVectorizerTool()
        self.governor = GovernorAlignmentTool()
        self.monitor = PerformanceMonitorTool()
        self.checkpointer = CheckpointStateManagerTool()

    def run_cycle(self, raw_input):
        """-> {"ok": bool, "stage": where it stopped or "done", ...}. A stage that produces nothing stops the cycle and says so."""
        self.logger.info("Starting new factory cycle.")
        clean_data = self.sanitizer.process(raw_input)
        if not clean_data:
            return {"ok": False, "stage": "sanitize", "reason": "input rejected or empty"}
        mapped_data = self.mapper.execute(clean_data)
        if not mapped_data:
            return {"ok": False, "stage": "vocabulary", "reason": "no words mapped"}
        tokens = self.tokenizer.execute(mapped_data)
        if not tokens:
            return {"ok": False, "stage": "tokenize", "reason": "no tokens"}
        vectors = self.vectorizer.convert_to_vectors(tokens)
        if vectors is None:
            return {"ok": False, "stage": "vectorize", "reason": "vectorizer returned nothing"}
        if not self.governor.check_and_execute("PROCESS_DATA", "ACTIVE"):
            return {"ok": False, "stage": "governor", "reason": "blocked by the governor"}
        health = self.monitor.get_current_health()
        self.logger.info("Cycle health: %s", health)
        checkpoint = self.checkpointer.save({"input": raw_input, "tokens": tokens, "vector": vectors.tolist() if hasattr(vectors, "tolist") else vectors})
        self.logger.info("Factory cycle completed.")
        return {"ok": True, "stage": "done", "tokens": len(tokens), "vector_dim": len(vectors), "checkpoint": checkpoint}


if __name__ == "__main__":
    orchestrator = FactoryOrchestrator()
    result = orchestrator.run_cycle("Initializing Sovereign shift sequence.")
    print(result)
    sys.exit(0 if result["ok"] else 1)
