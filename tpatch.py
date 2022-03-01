import os
import sys
import shutil
import hashlib
import argparse

from titan.util import *
from titan.keystone import keystone
from titan.patches.m8 import KERNEL_PATCHES
from titan.patches.common import PatchType

VERSION = '1.0'
AUTHOR  = 'Markus Gaasedelen'

#------------------------------------------------------------------------------
# Xbox Kernel Patcher
#------------------------------------------------------------------------------

class TitanPatcher(object):

    def __init__(self, filepath=None, udma=2):
        self.filepath = filepath
        self._ks = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_32)
        self._fd = None

        assert 2 <= udma <= 5, f"Invalid UDMA mode ({udma})"
        self._udma = udma

        if filepath:
            self.patch_kernel(filepath)

    def patch_kernel(self, filepath, force=False):
        """
        Patch the given xboxkrnl.exe with TITAN.
        """
        print(f"[*] - Hashing kernel '{filepath}' to ensure compatibility")
        file_md5 = hashlib.md5(open(filepath, 'rb').read())
        digest = file_md5.hexdigest()

        # Titan is only supported for the M8 kernel (at least, for now)
        if digest != 'ca3264d9e41723d0b9ccfbc9b1241ee9':
            print(f"[!] - Unknown kernel (md5: {digest})")
            if not force:
                raise ValueError("Kernel hash mismatch (already modified? not m8plus?)")
            print("[*] - FORCING PATCH... CANNOT ENSURE KERNEL WILL BE STABLE")

        # open the given kernel image for modification
        self.filepath = filepath
        self._fd = open(filepath, 'r+b')

        # patch the kernel
        self._patch_m8()

    #--------------------------------------------------------------------------
    # Supported Kernels
    #--------------------------------------------------------------------------

    def _patch_m8(self):
        """
        Patch the M8 kernel with TITAN.
        """
        # Reuse memory space for preproduction(?) CPU microcode
        self._prep_cave(0x80061E24, 0x80062624)

        for patch in KERNEL_PATCHES:
            patch_name = patch.__name__.split('Patch_')[1] + '(...)'
            print(f"[*] - 0x{patch.HOOK_ADDRESS:08X}: Patching {patch_name}")

            #
            # apply the assortment of 'main' patches to the kernel image
            # currently opened by this script
            #

            if patch.TYPE == PatchType.INLINE:
                self._patch_inline(patch)
            elif patch.TYPE in [PatchType.JUMP, PatchType.CALL]:
                self._patch_trampoline(patch)
            else:
                raise ValueError(f"unknown patch type: {patch.TYPE}")

            #
            # every 'major' patch can include an additional set of fixups
            #
            # there is no formal specification or rules for these, but they
            # are generally more 'minor' tweaks to the same function that
            # seem silly to break out into separate patches
            #

            self._patch_fixups(patch)

        #
        # Patch higher UDMA mode (if configured)
        #

        if self._udma > 2:
            patch_address = 0x800553FE
            patch_bytes = self._assemble(f"push 0x{0x40+self._udma:02X}", patch_address)
            self._write_bytes(patch_bytes, patch_address)

    #--------------------------------------------------------------------------
    # Patch Application
    #--------------------------------------------------------------------------

    def _patch_inline(self, patch):
        """
        Apply a simple inline patch to the kernel.
        """
        patch_bytes = self._assemble(patch.ASSEMBLY, patch.HOOK_ADDRESS)
        assert(len(patch_bytes) == patch.EXPECTED_LENGTH)
        self._write_bytes(patch_bytes, patch.HOOK_ADDRESS)

    def _patch_trampoline(self, patch):
        """
        Apply a trampoline (call/jump) based patch to the kernel.
        """
        if patch.TYPE == PatchType.JUMP:
            patch_return = f'jmp    0x{patch.HOOK_RETURN:08X}'
        else:
            patch_return = f'ret'

        patch_code = patch.ASSEMBLY + patch_return
        trampoline_target = self._patch_cave(patch_code)

        if patch.TYPE == PatchType.JUMP:
            trampoline_code = f'jmp     0x{trampoline_target:08X}'
        else:
            trampoline_code = f'call    0x{trampoline_target:08X}'

        # assemble & patch in the actual trampoline
        trampoline_bytes = self._assemble(trampoline_code, patch.HOOK_ADDRESS)
        self._write_bytes(trampoline_bytes, patch.HOOK_ADDRESS)

    def _patch_cave(self, code):
        """
        Assemble and patch code into the kernel cave and return its address.
        """
        current_address = self._current_cave_address

        # assemble the code that will be written into the code cave
        patch_bytes = self._assemble(code, current_address)
        if len(patch_bytes) + current_address > self._end_cave_address:
            raise RuntimeError("Ran out of code cave for patches...")

        # write the patch into the code cave
        self._write_bytes(patch_bytes, current_address)
        self._current_cave_address += len(patch_bytes)

        # maintain 16 byte alignment for cave patches (easier to debug/RE)
        self._current_cave_address = align16(self._current_cave_address)

        # return the address the assembled code was written into the code cave
        return current_address

    def _patch_fixups(self, patch):
        """
        Apply secondary fixups that may be included with a patch.
        """
        for fixup_address, fixup_code in patch.FIXUPS.items():
            patch_bytes = self._assemble(fixup_code, fixup_address)
            self._write_bytes(patch_bytes, fixup_address)

    #--------------------------------------------------------------------------
    # Patch Helpers
    #--------------------------------------------------------------------------

    def _assemble(self, code, address):
        """
        Return assembled bytes for the given instruction text (code).
        """

        # remove 'comments' from the assembly text
        cleaned_code = '\n'.join([line.split(';')[0] for line in code.splitlines()])

        # assemble instruction text
        asm_data, _ = self._ks.asm(cleaned_code, address, True)
        #print(f" - BYTES {hexdump(asm_data[:16])} {'...' if len(asm_data) > 16 else ''}")
        #print(f" -   LEN {len(asm_data)}")

        # return the resulting bytes
        return asm_data

    def _prep_cave(self, address_start, address_end):
        """
        Initialize a kernel code cave where larger patches will reside.
        """
        cave_size = address_end - address_start
        cave_trap = b'\xCC' * cave_size
        self._write_bytes(cave_trap, address_start)
        self._current_cave_address = align16(address_start)
        self._end_cave_address = address_end

    def _write_bytes(self, patch_bytes, patch_address):
        """
        Write bytes at the given kernel virtual address.
        """
        KERNEL_BASE = 0x80010000

        # translate patch RVA to file offset and seek to it
        file_offset = patch_address - KERNEL_BASE
        self._fd.seek(file_offset)

        # write patch into kernel image
        self._fd.write(patch_bytes)

#------------------------------------------------------------------------------
# Main
#------------------------------------------------------------------------------

def main(argc, argv):
    """
    Script main.
    """

    #
    # define script arguments
    #

    parser = argparse.ArgumentParser(
        prog='tpatch',
        usage='%(prog)s [options] kernel_filepath',
        description=f'Xbox kernel patcher for the Titan v{VERSION} HDD patchset',
    )

    parser.add_argument(
        'kernel_filepath',
        help='filepath to the target xboxkrnl.exe to patch'
    )

    parser.add_argument(
        '-u',
        '--udma',
        help='specify a UDMA mode (2 through 5)',
        default=2 # UDMA MODE 2 (retail)
    )

    parser.add_argument(
        '-f',
        '--force',
        help='forcefully patch the kernel image (ignore hash validation)',
        action='store_true',
        default=False
    )

    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-V', '--version', action='version')
    parser.version = f'Titan v{VERSION}'

    #
    # process script arguments
    #

    args = parser.parse_args()

    kernel_filepath = args.kernel_filepath
    kernel_filepath_bak = os.path.splitext(kernel_filepath)[0] + '.bak'

    # attempt to create a backup of the kernel (if it does not exist already)
    try:
        if not os.path.exists(kernel_filepath_bak):
            shutil.copy(kernel_filepath, kernel_filepath_bak)
    except:
        pass

    print(f"[*] Patching with Titan v{VERSION} -- by {AUTHOR}")

    # attempt to patch the given kernel image
    patcher = TitanPatcher(udma=args.udma)
    patcher.patch_kernel(kernel_filepath, args.force)

    print("[+] Patching successful!")
    return 0

#------------------------------------------------------------------------------
# Global Runtime
#------------------------------------------------------------------------------

if __name__ == '__main__':
    result = main(len(sys.argv), sys.argv)
    sys.exit(result)
