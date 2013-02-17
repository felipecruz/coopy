class PrevalentError(Exception):
    """This error represents issues related to the nature of a prevalent
       system.
    """
    def __init__(self, *args, **kwargs):
        super(PrevalentError, self).__init__(*args, **kwargs)

