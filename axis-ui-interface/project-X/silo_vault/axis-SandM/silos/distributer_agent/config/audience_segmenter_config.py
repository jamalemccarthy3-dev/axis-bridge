class AudienceSegmenterConfig:
    def __init__(self):
        # Operational parameters for the Audience Segmenter
        self.CLUSTERING_ALGORITHM = "k-means"
        self.MIN_SEGMENT_SIZE = 50
        
        # Segmentation criteria
        self.INCLUDE_BEHAVIORAL_DATA = True
        self.INCLUDE_GEOGRAPHIC_DATA = False