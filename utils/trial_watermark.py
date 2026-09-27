def is_trial_mode(payment_status=None):
    """
    Check if user is in trial mode
    """
    if payment_status in [None, 'pending', 'trial']:
        return True
    return False
