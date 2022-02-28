#------------------------------------------------------------------------------
# Utils
#------------------------------------------------------------------------------

def hexdump(data, wrap=0):
    """
    Return a spaced string of printed hex bytes for the given data.
    """
    wrap = wrap if wrap else len(data)
    if not data:
        return ''

    lines = []
    for i in range(0, len(data), wrap):
        lines.append(' '.join(['%02X' % x for x in data[i:i+wrap]]))

    return '\n'.join(lines)

def align16(address):
    """
    Return the next 16 byte aligned address.
    """
    return (address + 0x10) & 0xFFFFFFF0