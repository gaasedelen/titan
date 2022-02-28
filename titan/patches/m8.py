from .common import XboxPatch, PatchType

#-----------------------------------------------------------------------------
# M8+ Patch Definitions
#-----------------------------------------------------------------------------

class Patch_HddStartVerify(XboxPatch):
    TYPE = PatchType.INLINE
    HOOK_ADDRESS = 0x800243AA

    EXPECTED_LENGTH = 1
    ASSEMBLY = \
    """
    int3
    """

class Patch_HddVerify(XboxPatch):
    TYPE = PatchType.INLINE
    HOOK_ADDRESS = 0x8002443F

    EXPECTED_LENGTH = 1
    ASSEMBLY = \
    """
    int3
    """

class Patch_HddCompleteRw(XboxPatch):
    TYPE = PatchType.INLINE
    HOOK_ADDRESS = 0x80024485

    EXPECTED_LENGTH = 78
    ASSEMBLY = \
    """

    ;
    ; this may look like a lot, but it is mostly the original code
    ; with a few things moved around so the tweaks can fit as a
    ; native inline patch
    ;

    loc_one:
        mov     eax, [esi+4]
        and     eax, 0FFFFFFF8h
        cmp     eax, 20000h
        jbe     loc_three
        call    0x80014FBA
        test    al, al
        jz      loc_two
        pop     edi
        pop     esi
        jmp     0x80024E48

    loc_two:
        add     dword ptr [esi+4], 0FFFE0000h
        add     dword ptr [esi+10h], 20000h
        add     dword ptr [esi+0Ch], 20h
        push    edi
        push    dword ptr [esi+14h]
        call    dword ptr ds:[0x8003BD30]
        jmp     loc_four

    loc_three:
        mov     [esi+4], eax
        nop
        nop
        and     dword ptr [edi+10h], 0
        mov     dl, 1
        mov     ecx, edi
        call    0x8001660E
        nop

    loc_four:
    """

class Patch_HddStartRw_Length(XboxPatch):
    TYPE = PatchType.CALL
    HOOK_ADDRESS = 0x800244E6

    ASSEMBLY = \
    """
    ; clobbered by hook
    mov     eax, 20000h

    ; TransferLength = IRP->Parameters.HddRw.Length & 0xFFFFFFF8
    and     edi, 0xFFFFFFF8
    """

class Patch_HddStartRw_Transfer(XboxPatch):
    TYPE = PatchType.JUMP
    HOOK_ADDRESS = 0x80024534
    HOOK_RETURN  = 0x80024560

    # ~120 bytes
    ASSEMBLY = \
    """

    ;
    ; StartingSector = IRP->Parameters.HddRw.StartingSector
    ; StartingSector <<= 3
    ;

        mov     ebx, [esi+0Ch]        ; ebx = StartingSector (in 4K)
        xor     ecx, ecx
        shld    ecx, ebx, 3
        shl     ebx, 3                ; ecx:ebx = StartingSector (ecx = upper32, ebx = lower32)

    ;
    ; if (IRP->Parameters.HddRw.Length & 0x7)
    ;

        mov     eax, [esi+4]          ; eax = Length (in bytes)
        and     eax, 7
        jz      Lba48Transfer

    ;
    ; StartingSector += (IRP->Parameters.HddRw.Length & 0x7);
    ;

        add     ebx, eax
        adc     ecx, 0

    ;
    ; Lba48Transfer(HDD_DEVICE_NUMBER, StartingSector, SectorCount)
    ;
    ;   ecx:ebx = StartingSector  (in 512 sectors)
    ;       edi = TransferLength   (in bytes)
    ;

    Lba48Transfer:

    ; - WriteSectorCountPort((SectorCount & 0xFF00) >> 8));
        mov     eax, edi
        shr     eax, 11h
        mov     dx, 1F2h
        out     dx, al

    ; - WritePortByte(LBA48_LOW_REGISTER, (StartingSector & 0xFF000000) >> 24);
        mov     edx, ecx
        mov     eax, ebx
        shrd    eax, edx, 18h
        shr     edx, 18h
        mov     dx, 1F3h
        out     dx, al

    ; - WritePortByte(LBA48_MID_REGISTER, (StartingSector & 0xFF00000000) >> 32);
        mov     al, cl
        inc     dx
        out     dx, al

    ; - WritePortByte(LBA48_HIGH_REGISTER, (StartingSector & 0xFF0000000000) >> 40));
        mov     eax, ecx
        shr     eax, 8
        mov     dx, 1F5h
        out     dx, al

    ; - WriteSectorCountPort(SectorCount & 0xFF);
        add     dx, 0FFFDh
        mov     eax, edi
        shr     eax, 9
        out     dx, al

    ; - WritePortByte(LBA48_LOW_REGISTER, (sector & 0xFF));
        mov     dx, 1F3h
        mov     al, bl
        out     dx, al

    ; - WritePortByte(LBA48_MID_REGISTER, (sector & 0xFF00) >> 8);
        mov     edx, ecx
        mov     eax, ebx
        shrd    eax, edx, 8
        shr     edx, 8
        mov     dx, 1F4h
        out     dx, al

    ; - WritePortByte(LBA48_HIGH_REGISTER, (sector & 0xFF0000) >> 16);
        mov     eax, ebx
        shrd    eax, ecx, 10h
        shr     ecx, 10h
        inc     dx
        out     dx, al

    ; - WriteDeviceSelectPort(HDD_DEVICE_NUMBER);
        mov     dx, 1F6h
        mov     al, 40h
        out     dx, al

    ; 'fixup' for what the code normally expect dx to be on return
        mov     dx, 1F2h
    """

    FIXUPS = {
        0x8002456A: "mov    al, 0x25",
        0x80024571: "mov    al, 0x35"
    }

class Patch_HddRw_Save(XboxPatch):
    TYPE = PatchType.CALL
    HOOK_ADDRESS = 0x80024632

    ASSEMBLY = \
    """
    ; clobbered by hook
    adc     edx, dword ptr [ebp-4]

    ; 4K shift (also, clobbered, technically)
    mov     cl, 12

    ; save lower32 of StartOffset back to stack
    mov     [ebp-8], eax
    """

class Patch_HddRw_Smuggle(XboxPatch):
    TYPE = PatchType.JUMP
    HOOK_ADDRESS = 0x8002465B
    HOOK_RETURN = HOOK_ADDRESS + 7

    ASSEMBLY = \
    """
    ; clobbered by hook
    mov     eax, [edi+5Ch]
    or      byte ptr [eax+3], 1

    ; fetch lower32 of StartOffset
    mov     eax, dword ptr [ebp-8]

    ; compute remaining 512 segments
    shr     eax, 9
    and     eax, 7

    ; smuggle remaining segments through length field
    or      dword ptr [esi+4], eax
    """

class Patch_HddGetDriveGeometry(XboxPatch):
    TYPE = PatchType.JUMP
    HOOK_ADDRESS = 0x800246F3
    HOOK_RETURN  = 0x80024702

    ASSEMBLY = \
    """
    mov     edx, dword ptr ds:[0x8003C3B8]
    mov     eax, [ecx+30h]
    mov     [eax], edx
    mov     edx, dword ptr ds:[0x8003C3B8+4]
    mov     [eax+4], edx
    """

class Patch_HddPartitionCreate(XboxPatch):
    TYPE = PatchType.JUMP
    HOOK_ADDRESS = 0x8002F066
    HOOK_RETURN = 0x8002F07C

    ASSEMBLY = \
    """

    ; eax:edx = g_HddSectors
    load_size:
        mov     edx, dword ptr ds:[0x8003C3B8+4]
        mov     eax, dword ptr ds:[0x8003C3B8]

    ;
    ; Check if g_HddSectors appears larger than what is normally
    ; used by retail systems (0xEE8AB0 sectors)
    ;

    test_upper:
        test    edx, edx
        jnz     compute_f_length    ; upper32 bits set, clearly non-retail hdd

    test_lower:
        cmp     eax, 0xEE8AB0
        jbe     0x8002F05C          ; retail, do not honor the partition creation request

    compute_f_length:

        ; push SectorSize (64bit)
        push    0
        push    0x200

        ; push g_HddSectors (64bit)
        push    edx
        push    eax

        ; mul64(g_HddSectors, SectorSize)
        call    0x8002E030
    """

class Patch_HddCreateQuick(XboxPatch):
    TYPE = PatchType.JUMP
    HOOK_ADDRESS = 0x80024B5A
    HOOK_RETURN  = 0x80024B61

    ASSEMBLY = \
    """
    ; save ecx (will get clobbered by mul64)
    push    ecx

    ; push SectorSize (64bit)
    xor     esi, esi    ; esi also needs to be 0, returning from this patch
    push    esi
    push    edx         ; edx is 512 (a.k.a, standard sector size)

    ; push g_HddSectors (64bit)
    mov     edx, dword ptr ds:[0x8003C3B8+4]
    mov     eax, dword ptr ds:[0x8003C3B8]
    push    edx
    push    eax

    ; mul64(g_HddSectors, SectorSize)
    call    0x8002E030

    ; restore ecx
    pop ecx
    """

class Patch_HddCreate(XboxPatch):
    TYPE = PatchType.CALL
    HOOK_ADDRESS = 0x8005546D

    ASSEMBLY = \
    """
    ; eax:ecx = IdentifyData.Max48BitLBA
    mov     eax, dword ptr [ebp-0x160]
    mov     ecx, dword ptr [ebp-0x15C]

    ; ULONGLONG g_HddSectors = eax:ecx
    mov     dword ptr ds:[0x8003C3B8], eax
    mov     dword ptr ds:[0x8003C3B8+4], ecx
    """

class Patch_FatxParseSupeblock(XboxPatch):
    TYPE = PatchType.JUMP
    HOOK_ADDRESS = 0x80027143
    HOOK_RETURN = 0x800271D9

    ASSEMBLY = \
    """
    ; 128 clusters per sector
    jz      0x80027149

    ; 256 clusters per sector
    sub     ecx, 128
    jz      0x80027149

    ; 512 clusters per sector
    sub     ecx, 256
    jz      0x80027149

    ; 1024 clusters per sector
    sub     ecx, 512
    jz      0x80027149
    """

class Patch_FatxStartAsyncIo(XboxPatch):
    TYPE = PatchType.JUMP
    HOOK_ADDRESS = 0x80029CE5
    HOOK_RETURN  = 0x80029CFB

    ASSEMBLY = \
    """
    ;
    ; ebx = PhysicalLen
    ; eax = VolInfo
    ; edx = IoEntry
    ;

    ; ExtraSectors = IoLength & 7
    mov     ecx, ebx
    and     ecx, 7

    ;
    ; remove smuggled bits from IoLength
    ;
    ; PhysicalLen &= 0xFFFFFFF8
    ; IoEntry->PhysicalLen = PhysicalLen
    ;

    and     ebx, 0xFFFFFFF8
    mov     [edx+4], ebx

    ; AsyncDescriptor->LenRemaining -= PhysicalLen
    sub     [esi+8], ebx

    ; eax = VolInfo->SectorShift
    movzx   eax, byte ptr [eax+20h]

    ; ExtraSectorBytes = ExtraSectors << Volume->SectorShift
    xchg    eax, ecx
    shl     eax, cl
    xchg    eax, ecx

    ; this is just temporary storage :-)
    ; NextIRP->Parameters.Read.ByteOffset.Lower32 = ExtraSectorBytes
    mov     [edi+0Ch], ecx

    ; BigSectorShift = SectorShift + 3
    ; ecx = BigSectorShift
    add     eax, 3
    mov     ecx, eax

    ; result = (ULONGLONG)IoEntry->PhysicalSector << BigSectorShift
    mov     eax, [edx]
    xor     edx, edx
    call    0x8002E4C0      ; eax:edx = result

    ; NextIRP->Parameters.Read.ByteOffset.QuadPart = result + ExtraSectorBytes
    add     [edi+0Ch], eax
    adc     edx, 0
    mov     [edi+10h], edx
    """

class Patch_FatxAsyncIo(XboxPatch):
    TYPE = PatchType.CALL
    HOOK_ADDRESS = 0x80029E5B

    ASSEMBLY = \
    """
    ; eax = (ULONG)(PhysicalOffset >> (VolInfo->SectorShift + 3))
    add     ecx, 3
    call    0x8002E4A0

    ; PhysicalLen |= ((ULONG)(PhysicalOffset >> VolInfo->SectorShift) & 7)
    mov     edx, [ebp-18h]              ; edx  = PhysicalOffset
    mov     cl, byte ptr [edi+20h]      ;  cl = VolInfo->SectorShift
    shr     edx, cl                     ; edx >>= VolInfo->SectorShift
    and     edx, 7                      ; edx &= 7
    or      [ebp+1Ch], edx              ; PhysicalLen |= edx
    """

#-----------------------------------------------------------------------------
# Enumerate Patches
#-----------------------------------------------------------------------------

KERNEL_PATCHES = \
[
    # TODO: these should probably patched for completeness but appear unused
    Patch_HddStartVerify,
    Patch_HddVerify,

    # LBA48 + sector expansion
    Patch_HddStartRw_Length,
    Patch_HddStartRw_Transfer,
    Patch_HddRw_Save,
    Patch_HddRw_Smuggle,
    Patch_HddCompleteRw,

    # expand g_HddSectors to 64bit
    Patch_HddGetDriveGeometry,
    Patch_HddPartitionCreate,
    Patch_HddCreateQuick,
    Patch_HddCreate,

    # allow larger cluster sizes (up to 512kb)
    Patch_FatxParseSupeblock,

    # smuggle sector bits for async disk IO
    Patch_FatxStartAsyncIo,
    Patch_FatxAsyncIo
]