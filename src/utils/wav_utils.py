"""WAV file manipulation utilities."""
import struct
from pathlib import Path
from typing import List
import logging

logger = logging.getLogger(__name__)


def combine_wav_chunks(chunk_paths: List[Path]) -> bytes:
    """
    Combine multiple WAV chunks into a single WAV file.

    All chunks must have the same format (16-bit PCM, mono, 16kHz).
    Extracts PCM data from each chunk and concatenates, then adds proper header.

    Args:
        chunk_paths: List of paths to WAV chunk files

    Returns:
        bytes: Complete WAV file data
    """
    if not chunk_paths:
        raise ValueError("No chunks to combine")

    # Read first chunk to get format info
    with open(chunk_paths[0], 'rb') as f:
        first_chunk = f.read()

    # Validate WAV header
    if not validate_wav_header(first_chunk):
        raise ValueError(f"Invalid WAV header in {chunk_paths[0]}")

    # Extract format info from first chunk (bytes 20-35)
    audio_format = struct.unpack('<H', first_chunk[20:22])[0]  # Should be 1 (PCM)
    num_channels = struct.unpack('<H', first_chunk[22:24])[0]  # Should be 1 (mono)
    sample_rate = struct.unpack('<I', first_chunk[24:28])[0]   # Should be 16000
    byte_rate = struct.unpack('<I', first_chunk[28:32])[0]
    block_align = struct.unpack('<H', first_chunk[32:34])[0]
    bits_per_sample = struct.unpack('<H', first_chunk[34:36])[0]  # Should be 16

    logger.info(
        f"Combining {len(chunk_paths)} chunks: "
        f"{sample_rate}Hz, {bits_per_sample}-bit, {num_channels} channel(s)"
    )

    # Collect PCM data from all chunks (skip 44-byte headers)
    pcm_data = bytearray()
    for chunk_path in chunk_paths:
        with open(chunk_path, 'rb') as f:
            chunk_data = f.read()
            if len(chunk_data) > 44:
                pcm_data.extend(chunk_data[44:])  # Skip WAV header

    # Build complete WAV file with proper header
    data_size = len(pcm_data)
    file_size = data_size + 36  # Total size minus 8 bytes

    # Construct WAV header
    header = bytearray()
    header.extend(b'RIFF')
    header.extend(struct.pack('<I', file_size))
    header.extend(b'WAVE')
    header.extend(b'fmt ')
    header.extend(struct.pack('<I', 16))  # fmt chunk size
    header.extend(struct.pack('<H', audio_format))
    header.extend(struct.pack('<H', num_channels))
    header.extend(struct.pack('<I', sample_rate))
    header.extend(struct.pack('<I', byte_rate))
    header.extend(struct.pack('<H', block_align))
    header.extend(struct.pack('<H', bits_per_sample))
    header.extend(b'data')
    header.extend(struct.pack('<I', data_size))

    # Combine header + PCM data
    complete_wav = bytes(header) + bytes(pcm_data)

    logger.info(f"Combined WAV: {len(complete_wav)} bytes ({data_size} PCM bytes)")
    return complete_wav


def validate_wav_header(data: bytes) -> bool:
    """Validate WAV file header."""
    if len(data) < 44:
        return False

    # Check RIFF header
    if data[0:4] != b'RIFF':
        return False

    # Check WAVE format
    if data[8:12] != b'WAVE':
        return False

    return True
