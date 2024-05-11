import myzlib
import zlib
import sys
import os
import matplotlib.pyplot as plt
import numpy as np

PNG_HEADER = b'\x89\x50\x4E\x47\x0D\x0A\x1A\x0A'

def Check_PNG(data):
    # Check ancillary chunks (Header, IHDR, IDAT, IEND), exclude the PLTE chunk
    header = data[:8]

    # Check PNG header
    if header != PNG_HEADER:
        raise Exception('Invalid PNG signature: {}'.format(header))
    
    # Check IHDR chunk
    try:
        IHDR_id = data.index(b'IHDR')
        IHDR_data = read_chunk(data, IHDR_id)
    except Exception as e:
        if e == 'ValueError: substring not found':
            raise Exception('Invalid IHDR chunk')
        else:
            raise e

    # Check IDAT chunk
    try:
        IDAT_id = data.index(b'IDAT')
        IDAT_stream = process_IDAT(data, IDAT_id)
    except Exception as e:
        if e == 'ValueError: substring not found':
            raise Exception('Invalid IDAT chunk')
        else:
            raise e

    # Check IEND chunk
    try:
        IEND_id = data.index(b'IEND')
        IEND_data = read_chunk(data, IEND_id)
        if len(IEND_data) > 0:
            print("Trailer data after IEND chunk, but not spoil the picture's pixels: {}".format(IEND_data))
    except Exception as e:
        if e == 'ValueError: substring not found':
            raise Exception('Invalid IDAT chunk')
        else:
            raise e

    return IHDR_data, IDAT_stream

def read_chunk(data, id):
    # Check len and checksum in a chunk
    # Return the chunk's data
    chunk_type = data[id:id+4]
    len = int.from_bytes(data[id-4:id])
    chunk_data = data[id+4:id+4+len]
    crc_data = data[id+4+len:id+4+len+4]
    crc_data = int.from_bytes(crc_data, byteorder='big')
    check_crc = zlib.crc32(chunk_type + chunk_data)
    
    if check_crc != crc_data:
        raise Exception('chunk checksum failed: check_crc != crc_data')
    
    return chunk_data     
   
def process_IDAT(data, IDAT_id):
    id = IDAT_id
    IDAT_stream = []
    while True:
        IDAT_stream.append(read_chunk(data, id))
        chunklen = len(IDAT_stream[-1]) + 4 + 8     # len of "IDAT" + data + Checksum(4 byte) + len_of_next_chunk (4 byte)
        id += chunklen      # next id of the next chunk
        # The IDAT chunks must be consecutive in PNG file
        # If the next chunk is not IDAT, mean the previous the last IDAT chunk so break the loop
        if (data[id:id+4] != b'IDAT'):
            break
    return b''.join(IDAT_stream)    
    
def byte2int(data):
    return int.from_bytes(data, byteorder='big')

def read_IHDR(data):
    width = byte2int(data[:4])
    height = byte2int(data[4:8])
    bitdepth = data[8]
    color_type = data[9]
    compression_method = data[10]
    filter_method = data[11]
    interlace = data[12]
    if compression_method != 0:
        raise Exception('Invalid compression method')
    if filter_method != 0:
        raise Exception('Invalid filter method')
    if color_type != 6 and color_type != 2:
        raise Exception('Only support truecolor with alpha (RGBA) and (RGB): color_type = {}'.format(color_type))
    elif color_type == 6:
        byte_per_pixel = 4
    else:
        byte_per_pixel = 3
    if bitdepth != 8:
        raise Exception('Only support a bit depth of 8')
    if interlace != 0:
        raise Exception('Only support no interlacing')
    return width, height, byte_per_pixel

## Filter Algorithm

class Filter:
    def __init__(self, width, height, bytes_per_pixel, idat_data):
        self.width = width
        self.height = height
        self.bytes_per_pixel = bytes_per_pixel
        self.idat_data = idat_data
        self.stride = width * bytes_per_pixel
        self.recon = []

    def recon_a(self, r, c):
        return self.recon[r * self.stride + c - self.bytes_per_pixel] if c >= self.bytes_per_pixel else 0

    def recon_b(self, r, c):
        return self.recon[(r - 1) * self.stride + c] if r > 0 else 0

    def recon_c(self, r, c):
        return self.recon[(r - 1) * self.stride + c - self.bytes_per_pixel] if r > 0 and c >= self.bytes_per_pixel else 0

    def paeth_predictor(self, a, b, c):
        p = a + b - c
        pa = abs(p - a)
        pb = abs(p - b)
        pc = abs(p - c)
        if pa <= pb and pa <= pc:
            return a
        elif pb <= pc:
            return b
        else:
            return c

    def re_filter(self):
        i = 0
        for r in range(self.height):
            filter_type = self.idat_data[i]
            i += 1
            for c in range(self.stride):
                filt_x = self.idat_data[i]
                i += 1
                if filter_type == 0:  # None
                    recon_x = filt_x
                elif filter_type == 1:  # Sub
                    recon_x = filt_x + self.recon_a(r, c)
                elif filter_type == 2:  # Up
                    recon_x = filt_x + self.recon_b(r, c)
                elif filter_type == 3:  # Average
                    recon_x = filt_x + (self.recon_a(r, c) + self.recon_b(r, c)) // 2
                elif filter_type == 4:  # Paeth
                    recon_x = filt_x + self.paeth_predictor(self.recon_a(r, c), self.recon_b(r, c), self.recon_c(r, c))
                else:
                    raise Exception('unknown filter type: ' + str(filter_type))
                self.recon.append(recon_x & 0xff)  # truncation to byte
        return self.recon

if __name__ == "__main__":
    file_path = sys.argv[1].strip()
    if not os.path.exists(file_path):
        raise Exception('File path does not exist!')
    data = open(file_path, 'rb').read()
    # Assuming the methods Check_PNG and read_IHDR are defined elsewhere to extract relevant information
    IHDR_data, IDAT_stream = Check_PNG(data)
    width, height, bytes_per_pixel = read_IHDR(IHDR_data)
    filtered_pixel_data = myzlib.decompress(IDAT_stream)
    filter_obj = Filter(width, height, bytes_per_pixel, filtered_pixel_data)
    raw_pixel_data = filter_obj.re_filter()

    plt.axis("off")
    plt.imshow(np.array(raw_pixel_data).reshape(height, width, bytes_per_pixel))
    plt.show()