class BitReader:
    def __init__(self, mem):
        self.mem = mem
        self.byte_pos = 0
        self.byte = 0
        self.bit_pos = 0

    def read_byte(self):
        # Read bytes from left -> right
        self.bit_pos = 0
        b = self.mem[self.byte_pos]
        self.byte_pos += 1
        return b
    
    def read_bit(self):
        # Read bit from right -> left
        if self.bit_pos <= 0:
            self.byte = self.read_byte()
            self.bit_pos = 8
        self.bit_pos -= 1
        bit = self.byte & 1
        self.byte >>= 1    # Shift the readed bit out of the byte
        return bit
    
    def read_bits(self, N):
        # Read a N number of bits from right -> left and reverse theirs order
        bits = 0 
        for i in range(N):
            bits |= self.read_bit() << i
        return bits
    
    def read_bytes(self, N):
        # Read a N number of bytes from left -> right
        out = 0
        for i in range(out):
            out |= self.read_byte() << (8 * i)
        return out
    
class Node:
    def __init__(self):
        self.symbol = ''
        self.left = None
        self.right = None

class HuffmanTree:
    def __init__(self):
        self.root = Node()
        self.root.symbol = ''

    def insert(self, huffman_code, code_len, alphabet):
        # Start from root
        node = self.root
        # Read bits in huffman code from left -> right 
        # bit = 1 -> Right Node
        # bit = 0 -> Left Node
        ## print('huff_code: ', huffman_code)
        for i in range(0, code_len):
            bit = (huffman_code >> (code_len - 1 - i)) & 1
            #print(bit, end=" ")
            ## print("l" if not bit else "r", end=" ")
            if bit:
                if node.right == None:
                    node.right = Node()
                next_node = node.right
            else:
                if node.left == None:
                    node.left = Node()
                next_node = node.left
            node = next_node
        ## print('\n')
        node.symbol = alphabet
        ## print(node.symbol, end=" ")
        

CLEN_CODE_ORDER = [16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15]

def preprocessing(r):
    # Preprocessing info data appeared before compressed data in a block to build Huffman tree => retrieve Huffman code (symbol) for each character

    # Code lengths for the literal/length alphabet, encoded using the code length Huffman code
    HLIT = r.read_bits(5) + 257
    # Code lengths for the distance alphabet, encoded using the code length Huffman code
    HDIST = r.read_bits(5) + 1
    # Code lengths for "code length" alphabet, used to compress code lengths for literal/length and distance alphabet
    HCLEN = r.read_bits(4) + 4

    code_length_bl = [0 for i in range(19)]
    for i in range(HCLEN):
        code_length_bl[CLEN_CODE_ORDER[i]] = r.read_bits(3)

    code_length_tree = build_tree(code_length_bl, range(19))

    # Read literal/length and distance code length list
    bl = []
    while len(bl) < HLIT + HDIST:
        symbol = decode_symbol(r, code_length_tree)
        if symbol <= 15:
            bl.append(symbol)
        elif symbol == 16:
            tmp = bl[-1]
            repeat = r.read_bits(2) + 3
            for i in range(repeat-1):
                bl.append(tmp)
        elif symbol == 17:
            tmp = bl[-1]
            repeat = r.read_bits(3) + 3
            for i in range(repeat-1):
                bl.append(tmp)
        elif symbol == 18:
            tmp = bl[-1]
            repeat = r.read_bits(7) + 11
            for i in range(repeat-1):
                bl.append(tmp)

    # Build trees:
    literal_length_tree = build_tree(bl[:HLIT], range(286))
    distance_tree = build_tree(bl[HLIT:], range(30))
    return literal_length_tree, distance_tree

def build_tree(bl, alphabet):
    # bl: bit lens of each symbol of each alphabet (in alphabetically order)
    # Step 1: Create bl_count[i] as the number of the bit len of i exists in bl
    # Step 2: Find the numerical value of the smallest code for each bit len
    # Step 3: Assign numerical values to all bit lens (Assign each alphabet into its correct position in Huffman Tree)

    MAX_BITS = max(bl)
    bl_count = [0] * (MAX_BITS+1)
    for i in range(1, MAX_BITS+1):      # code_len_of_a_character = i = 0: This character not exists in Huffman Tree 
        for j in bl:
            if j==i:
                bl_count[i] += 1
    ## print("bl_count: ", bl_count)
    base_code = [0]
    for bits in range(1, MAX_BITS+1):
        base_code.append((base_code[bits-1] + bl_count[bits-1]) * 2)

    ## print(base_code)
    tree = HuffmanTree()
    for a, bitlen in zip(alphabet, bl):
        if bitlen == 0:
            continue
        tree.insert(base_code[bitlen], bitlen, a)
        base_code[bitlen] += 1
    return tree


def decode_symbol(r, huffman_tree):
    # Decode compressed data to symbol using Huffman tree
    node = huffman_tree.root
    while node.left or node.right:
        bit = r.read_bit()
        if (bit):
            node = node.right
        else:
            node = node.left
    print("symbol:", node.symbol)
    return node.symbol


def decompress(input):
    # Zlib Decompress
    r = BitReader(input)
    CMF = r.read_byte()
    CM = CMF & 15
    if CM != 8:     # Compression method 8 => Deflate compressed data format
        raise Exception('Invalid compression method in PNG: CM={}'.format(CM))
    CINFO = CMF >> 4
    if CINFO > 7:
        raise Exception('Invalid compression info: CINFO={}'.format(CINFO))
    FLG = r.read_byte()
    FCHECK = FLG & 31
    FDICT = (FLG >> 5) & 1
    FLEVEL = FLG >> 6   # Compression level => Not needed for decompression
    if (CMF * 256 + FLG) % 31 != 0:
        raise Exception('CMF and FLG check bits failed') 
    if FDICT:
        raise Exception('Non-supported dictionary preset')
    output = inflate(r)    
    ADLER32 = r.read_bytes(4)   # Adler-32 checksum: Checksum value of uncompressed data (excluding dictionary data)
    return bytes(output)

def inflate(r):
    output = []
    while True:
        BFINAL = r.read_bit()
        BTYPE = r.read_bits(2)
        if BTYPE == 0:
            inflate_block_no_compression(r, output)
        elif BTYPE == 1:
            inflate_block_fixed_huffman_code(r, output)
        elif BTYPE == 2:
            inflate_block_dynamic_huffman_code(r, output)
        else:
            raise Exception('Reserved (Error) BTYPE: BTYPE={}'.format(BTYPE))
        if BFINAL == 1:     # This is the last block
            break
    return output

def inflate_block_no_compression(r, output):
    LEN = r.read_bytes(2)
    NLEN = r.read_bytes(2)
    output.append(r.read_bytes(LEN))

def inflate_block_fixed_huffman_code(r, output):
    # Build literal/length tree
    bl = []
    for i in range(288):
        if (0 <= i < 144) or (280 <= i):
            bl.append(8)
        elif (144 <= i < 256):
            bl.append(9)
        else:   #256 <= i < 279
            bl.append(7)
    #print(bl)
    literal_length_tree = build_tree(bl, range(286))

    # Build distance tree
    bl = []
    bl = [5 for i in range(30)]
    distance_tree = build_tree(bl, range(30))
    #print_tree(distance_tree.root)
    #print(bl)
    inflate_block(r, output, literal_length_tree, distance_tree)

def print_tree(root):
    node = root
    while True:
        if node.left == None and node.right == None:
            return
        print(node.left.symbol,'\t', node.right.symbol, '\n')
        print_tree(node.left)
        print_tree(node.right)

def inflate_block_dynamic_huffman_code(r, output):
    literal_length_tree, distance_tree = preprocessing(r)
    inflate_block(r, output, literal_length_tree, distance_tree)

EXTRA_BITS_LENGTH = [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3,
        3, 4, 4, 4, 4, 5, 5, 5, 5, 0]
SMALLEST_LENGTH = [3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43,
        51, 59, 67, 83, 99, 115, 131, 163, 195, 227, 258]
EXTRA_BITS_DISTANCE = [0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7,
        8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13]
SMALLEST_DISTANCE = [1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257,
        385, 513, 769, 1025, 1537, 2049, 3073, 4097, 6145, 8193, 12289, 16385,
        24577]

def inflate_block(r, output, literal_length_tree, distance_tree):
    tmp = []
    while True:
        symbol = decode_symbol(r, literal_length_tree)
        if symbol <= 255:
            #tmp.append(symbol) 
            output.append(symbol)
        elif symbol == 256:     # End of block
            break
        else:       # <length, backward distance>
            symbol -= 257
            length = SMALLEST_LENGTH[symbol] + r.read_bits(EXTRA_BITS_LENGTH[symbol])
            distance = decode_symbol(r, distance_tree)
            distance = SMALLEST_DISTANCE[distance] + r.read_bits(EXTRA_BITS_DISTANCE[distance])
            for i in range(length):
                output.append(output[-distance])

    #output.extend(tmp)



import zlib
x = zlib.compress(b'the most expensive tour trip')
y = bytes.fromhex("08 D7 63 F8 CF C0 00 00 03 01 01 00")
print(decompress(y)) # b'Hello World!'