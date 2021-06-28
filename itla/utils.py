import yaml


def setup_registers():
    with open('registers.yaml', 'r') as yaml_file:
        yaml_dict = yaml.safe_load(yaml_file)
        registers = {key: yaml_dict[key]['register']
                     for key in yaml_dict.keys()}
        registers_inv = {registers[key]: key
                         for key in registers.keys()}

        return registers, registers_inv


def get_hexstring(register, data, header):
    """forms the hexstring for the command youre trying to send

    :param register: the register you want to write to
    :param data: the data to write to the register
    :param header: the header for the packet
    :returns: the hexstring for the command

    """

    # Each of these change the parameter to a hex and cut off the 0x part
    # It may be possible to remove the 0x parts by removing the '#'
    header_hex = f'{header:#04x}'[2:]
    register_hex = f'{register:#04x}'[2:]
    data_hex = f'{data:#06x}'[2:]

    return header_hex + register_hex + data_hex


def compute_checksum(hexstring):
    """ Computes the command checksum

    :param register: the register to write to
    :param data: the data to write the register
    :param write: whether or not you are writing to the register
    :returns: the checksum value

    """
    # get the hexstring for the command without the

    byte_list = bytes.fromhex(hexstring)

    bip8 = byte_list[0] & 15 ^ byte_list[1] ^ byte_list[2] ^ byte_list[3]

    return (bip8 & 240) >> 4 ^ bip8 & 15


def form_packet(register, data, write=False):
    """This computes the checksum and generates the hexstring.

    :param register: the register you want to write to.
    :param data: the data to write to that register
    :param write: true or false value for
    whether you are trying to write to the register
    :returns: the hexstring for the command you are sending

    """
    if data is None:
        data = 0

    if not isinstance(write, bool):
        raise TypeError('The variable `write` must be True or False')

    hexstring = get_hexstring(register, data, write)
    checksum = compute_checksum(hexstring)
    header = checksum * 16 + write

    hexstring = get_hexstring(register, data, header)

    return hexstring
