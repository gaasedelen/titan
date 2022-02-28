import enum

#------------------------------------------------------------------------------
# Common Patch Definitions
#------------------------------------------------------------------------------

class PatchType(enum.IntEnum):
    INVALID = 0
    INLINE  = 1
    JUMP    = 2
    CALL    = 3

class XboxPatch(object):

    # what type of patch this and where it should modify the kernel
    TYPE = PatchType.INVALID
    HOOK_ADDRESS = 0x00000000
    HOOK_RETURN = 0x00000000

    # patch data
    ASSEMBLY = ""
    FIXUPS = {}
