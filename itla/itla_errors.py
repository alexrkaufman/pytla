class StatusException(Exception):
    pass

class ExecutionError(StatusException):
    """Raised when XE response occurs"""
    pass


class AEAException(StatusException):
    """Raised when an AEA response occurs."""
    pass


class CPException(StatusException):
    """raised when a command pending response occurs"""
    pass

class NOPException(Exception):
    pass

class RNIError(NOPException):
    """NOP exception.
    RNI: Register not implemented."""
    pass

class RNWError(NOPException):
    """NOP exception.
    RNW: Register not writeable.
    """
    pass

class RVEError(NOPException):
    """NOP Exception
    RVE: Register value range error.
    """
    pass

class CIPError(NOPException):
    pass

class CIIError(NOPException):
    pass

class EREError(NOPException):
    pass

class EROError(NOPException):
    pass

class EXFError(NOPException):
    pass

class CIEError(NOPException):
    pass

class IVCError(NOPException):
    pass

class VSEError(NOPException):
    pass
