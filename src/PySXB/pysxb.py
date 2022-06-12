"""PySXB:  Basic python implementation of Terebium IDE, (TIDE). Based on the work of
Chris Baird <cjb@brushtail.apana.org.au> July 2019

David Couples
2021 November
"""

import serial
import sys


class PySXB(serial.Serial):
    """ PySXB:

    Args:
        cpu_mode =

    """
    INIT = (0x55, 0xAA)
    #  = 0x01
    WRITE = 0x02
    READ = 0x03
    TIDE = 0x04
    EXEC = 0x05
    BLK_SIZE = 62
    OK = 0xCC
    C02 = 0x2
    C816 = 0x1

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._rom = None
        self._tide_data = bytearray(self.tide())

    @property
    def rom(self):
        """Returns the program ROM
        
        Returns:
            bytearray: the data contained in "ROM"
        """
        return self._rom
    
    @rom.setter
    def rom(self, data_in):
        """Setter for "ROM"

        Args:
            data_in (bytearray): the rom image

        Returns:
            Nothing
        """
        self._rom = data_in
        
    @property
    def tide_data(self):
        """ returns the tide data

        Returns:

        """
        return self._tide_data
        
    def _command(self, cmd, length, base_address=None):

        if base_address:
            return self._instruction(cmd, base_address, length)

        if isinstance(cmd, (list, tuple)):
            self.write(cmd)
        else:
            self.write((cmd,))
            
        try:
            if length:
                return self.read(length)
            else:
                return None
        except serial.SerialTimeoutException as error:
            print(f"Error: {error}\n")
            sys.exit(1)
        except TypeError as error:
            print(f"Error: {error}\n")
            sys.exit(1)

    def _instruction(self, cmd, address, length):

        address_lo = address & 255
        address_hi = (address >> 8) & 255
        address_ba = (address >> 16) & 255

        length_lo = (length & 255)
        length_hi = (length >> 8) & 255
        seq = (cmd, address_lo, address_hi, address_ba, length_lo, length_hi)
        return self.write(seq) > 0

    @staticmethod
    def _address_decode(address):
        return_val = 0
        for i, address_byte in enumerate(address):
            return_val |= address_byte << i * 8

        return return_val

    @staticmethod
    def _address_encode(address):
        return (address & 255), ((address >> 8) & 255), ((address >> 16) & 255)

    def _vectors(self, offset):
        vector_address = self._address_decode(self._rom[offset: offset + 3])
        size = self._address_decode(self._rom[offset + 3: offset + 6])
        vectors = self._rom[offset + 6: offset + 6 + size]
        return vector_address, size, vectors

    def attention(self):   # REF: Hayes modem command set
        return ord(self._command(self.INIT, 1)) == self.OK

    def tide(self):
        if self.attention():
            return self._command(self.TIDE, 29)

        return None

    def write_mem(self, base_address, write_data):
        length = len(write_data)
        if self.attention():
            if self._command(self.WRITE, length, base_address):
                return self.write(write_data)
        return 0

    def read_mem(self, base_address, length):
        temp = bytearray(length)
        if self.attention():
            if self._command(self.READ, length, base_address):
                if length < self.BLK_SIZE:
                    return self.read(length)
                else:
                    for i in range(0, length, self.BLK_SIZE):
                        if i + self.BLK_SIZE < length:
                            temp[i: i + self.BLK_SIZE] = self.read(self.BLK_SIZE)
                        else:
                            temp[i:length] = self.read(length-i)
                return temp

        return None

    def execute(self, cpu_mode, base_address, length=2):
        exec_ba = (base_address >> 16) & 255
        exec_hi = (base_address >> 8) & 255
        exec_lo = base_address & 255

        state = (
            0, 0,               # A register (low, high) (Accumulator)
            0, 0,               # X register (low, high)
            0, 0,               # Y register (low, high)
            exec_lo, exec_hi,   # execution address (low, high)
            exec_ba,            # Bank address
            0x76,               # processor status register
            0,
            255,                # stack pointer
            0,                  # ?
            cpu_mode,           # cpu mode  0 = 65816 1 = 6502
            0,                  # B register
            0
        )

        self.write_mem(0x7e00, state)
        if self.attention():
            return self._command(self.EXEC, length)

    @staticmethod
    def print_hex(data, base=0):
        line = ""

        for i, datum in enumerate(data):

            if i % 16 == 0:
                line += f"\n{i+base:#06x}:"
            if (i % 8 == 0) and (i % 16 != 0):
                line += " "
            line += f" {datum:02X}"

        return line

    def load_program(self, file):
        
        if file:
            with open(file, 'rb') as fh:
                self._rom = fh.read()

        if self._rom[0] == 0x5a:     # checking for debug from the WDC02 assembler

            # bytes 1, 2, and 3 are the low, high, and bank (65816) addresses in the SXB's memory
            # where to start loading
            code_address = self._address_decode(self._rom[1:4])
            # byte 4 and 5 are the code length
            code_length = self._address_decode(self._rom[4:7])
            # byte 6 acts as an end of preamble marker?
            # load the code portion of the self._rom into the SXB
            code = self._rom[7:7+code_length]
            self.write_mem(code_address, code)

            # work on the shadow vectors.
            vector_base = 7 + code_length
            vector_address, vector_size, vectors = self._vectors(vector_base)
            self.write_mem(vector_address, vectors)

            vector_base += 6 + vector_size
            vector_address, _, vectors = self._vectors(vector_base)
            self.write_mem(vector_address, vectors)
        else:
            raise ValueError("Program needs to be compiled/assembled with the -g option")
