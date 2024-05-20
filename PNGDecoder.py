import myzlib
import zlib
import sys
import os
import matplotlib.pyplot as plt
import numpy as np
from colorama import init, Fore, Style
import time
from tqdm import tqdm

PNG_HEADER = b'\x89\x50\x4E\x47\x0D\x0A\x1A\x0A'
BANNER = """

██████╗ ███╗   ██╗ ██████╗     ██████╗ ███████╗ ██████╗ ██████╗ ██████╗ ███████╗██████╗ 
██╔══██╗████╗  ██║██╔════╝     ██╔══██╗██╔════╝██╔════╝██╔═══██╗██╔══██╗██╔════╝██╔══██╗
██████╔╝██╔██╗ ██║██║  ███╗    ██║  ██║█████╗  ██║     ██║   ██║██║  ██║█████╗  ██████╔╝
██╔═══╝ ██║╚██╗██║██║   ██║    ██║  ██║██╔══╝  ██║     ██║   ██║██║  ██║██╔══╝  ██╔══██╗
██║     ██║ ╚████║╚██████╔╝    ██████╔╝███████╗╚██████╗╚██████╔╝██████╔╝███████╗██║  ██║
╚═╝     ╚═╝  ╚═══╝ ╚═════╝     ╚═════╝ ╚══════╝ ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝
                                                                                        
MY SIMPLE PNG VIEWER
"""

def Check_PNG(data):
    """
    Check the  PNG file and extract it ancillary chunks'data.

    Args:
        data (bytes): The raw data of the PNG file.

    Returns:
        (tuple): A tuple contains the IHDR chunk's data and IDAT stream of data.
    """
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
    """
    Read data in one chunk from the PNG data.

    Args:
        data (bytes): The raw data of the PNG file
        id (int): The start index (offset) of the chunk in PNG file.

    Returns:
        (bytes): The data of the chunk.

    """
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
    """
    Process the IDAT chunks of a file: Merge the data of all IDAT chunks into a stream of data.

    Args:
        data (bytes): The raw data of PNG file.
        IDAT_id (int): The start index (offset) of the first IDAT chunk in PNG file.

    Returns:
        (bytes): The merged IDAT data stream.

    """
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

def read_IHDR(data):
    """
    Check the supported and validity type of image and extract metadata of PNG file from IHDR chunk data.

    Args:
        data (bytes): The IHDR chunk data.

    Returns:
        (tuple): A tuple contains the width, height, bitdepth (bytes per pixel) of the image.

    """
    width = int.from_bytes(data[:4], byteorder='big')
    height = int.from_bytes(data[4:8], byteorder='big')
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
        raise Exception('Only support truecolor with alpha RGBA and RGB: color_type = {}'.format(color_type))
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
    """
    This is a class to recover the non-filtered pixel data from filtered pixel data after zlib decompression operation from IDAT stream.

    Attributes:
        width (int): The width of the image (number of column in the pixel matrix)
        height (int): The height of the image (number of row in the pixel matrix)
        bytes_per_pixels (int): Number of byte to perform one pixel on the image.
        idat_data (bytes):  filtered pixel data.
        stride (int): number of bytes per row.
        recon (list): A list to store the reconstructed pixel data.

    """
    def __init__(self, width, height, bytes_per_pixel, idat_data):
        """
        Initialize the Filter object.

        Args:
            width (int): The width of the image (number of column in the pixel matrix)
            height (int): The height of the image (number of row in the pixel matrix)
            bytes_per_pixels (int): Number of byte to perform one pixel on the image.
            idat_data (bytes):  filtered pixel data.

        """
        self.width = width
        self.height = height
        self.bytes_per_pixel = bytes_per_pixel
        self.idat_data = idat_data
        self.stride = width * bytes_per_pixel
        self.recon = []

    def recon_a(self, r, c):
        """
        Get the value of the pixel to the left of the current pixel.

        Args:
            r (int): The row index of the current pixel.
            c (int): The column index of the current pixel.

        Returns:
            int: The value of the pixel to the left of the current pixel.
        """
        return self.recon[r * self.stride + c - self.bytes_per_pixel] if c >= self.bytes_per_pixel else 0

    def recon_b(self, r, c):
        """
        Get the value of the pixel above the current pixel.

        Args:
            r (int): The row index of the current pixel.
            c (int): The column index of the current pixel.

        Returns:
            int: The value of the pixel above the current pixel.

        """
        return self.recon[(r - 1) * self.stride + c] if r > 0 else 0

    def recon_c(self, r, c):
        """
        Get the value of the pixel to the upper left of the current pixel.

        Args:
            r (int): The row index of the current pixel.
            c (int): The column index of the current pixel.

        Returns:
            int: The value of the pixel to the upper left of the current pixel.

        """
        return self.recon[(r - 1) * self.stride + c - self.bytes_per_pixel] if r > 0 and c >= self.bytes_per_pixel else 0

    def paeth_predictor(self, a, b, c):
        """
        Calculate the Paeth predictor for the current pixel.

        Args:
            a (int): The value of the pixel to the left of the current pixel.
            b (int): The value of the pixel above the current pixel.
            c (int): The value of the pixel to the upper left of the current pixel.

        Returns:
            int: The predicted value for the current pixel.

        """
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
        """
        Recover the raw pixel data from filtered pixel data.

        Returns:
            (list): A list to store the raw pixel data

        """

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

def main(file_path):
    """
    Main function to decode and display a PNG image.
 
    Args:
        file_path (str): The path to the PNG file.
 
    Returns:
        A window to display a PNG image will be popped up
    """

    if not os.path.exists(file_path):
        raise FileNotFoundError('File path does not exist!')
    
    start = time.time()

    data = open(file_path, 'rb').read()
    # Assuming the methods Check_PNG and read_IHDR are defined elsewhere to extract relevant information
    IHDR_data, IDAT_stream = Check_PNG(data)
    width, height, bytes_per_pixel = read_IHDR(IHDR_data)
    
    filtered_pixel_data = myzlib.decompress(IDAT_stream)

    filter_obj = Filter(width, height, bytes_per_pixel, filtered_pixel_data)
    raw_pixel_data = filter_obj.re_filter()

    print(Fore.YELLOW + "Processing completed in {:.2f} seconds".format(time.time() - start))
    plt.axis("off")
    plt.imshow(np.array(raw_pixel_data).reshape(height, width, bytes_per_pixel))
    plt.show()

if __name__ == "__main__":
    init(autoreset = True)
    print(Fore.YELLOW  + BANNER)
    if len(sys.argv) < 2 :
        print(Fore.RED + '[+] Usage: PNGDecoder.py <filename>')
        sys.exit(1)
    file_path = sys.argv[1].strip()
    main(file_path)
    