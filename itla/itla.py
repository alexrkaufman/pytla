from pkg_resources import resource_filename
from .itla_errors import *
from .utils import compute_checksum
import yaml
import serial
from serial.serialutil import SerialException


class ITLABase():
    '''
    A class that represents the an ITLA
    and exposes a user friendly API for controlling functionality.

    Things to figure out

      * What should be exposed to the user?
      * Can we abstract away the concept of registers and stuff
        in here so you don't have to deal with it.

    There are some functions that could be implemented like set_fatalstatus.
    I think this is probably a bad idea even though it isnt write only.

    set_frequency is my platonic ideal for the higher level functions.
    '''

    _nop_errors = {
        0x00: 'OK: No errors.',
        0x01: RNIError('RNI: Register not implemented.'),
        0x02: RNWError('RNW: Register not writable'),
        0x03: RVEError('RVE: Register Value range Error.'),
        0x04: CIPError('CIP: Command Ignored due to Pending operation'),
        0x05: CIIError('CII: Command Ignored Initializing'),
        0x06: EREError('ERE: Extended address Range Error (address invalid)'),
        0x07: EROError('ERO: Extended address is read only'),
        0x08: EXFError('EXF: Execution general failure'),
        0x09: CIEError('CIE: Command ignored while module\'s optical output is enabled'),
        0x0A: IVCError('IVC: Invalid configuration command ignored.'),
        0x0F: VSEError('VSE: Vendor specific error')
    }

    _response_status = {
        0x00: 'OK',
        0x01: ExecutionError('Command returned execution error.'),
        0x02: AEAException('AEA: automatic extended addressing '
                           + 'being returned or ready to write.'),
        0x03: CPException('CP: Command not complete, pending.')
    }

    def __init__(self, serial_port, baudrate, timeout=0.5,
                 register_files=None):
        """TODO describe function

        :param serial_port:
        :param baudrate:
        :param timeout:
        :returns:

        """
        self._port = serial_port
        self._baudrate = baudrate
        self._timeout = timeout
        self._device = None

        if register_files is None:
            register_files = []

        # this function creates register functions
        def mkfn(*, fnname, register, description,
                 readonly, signed, **_):
            # _ here to absorb unused things. This way the yaml
            # can contain more info without causing errors here.
            if readonly:
                def reg_fun(self):
                    self.send_command(register, signed=signed)
                    return self.get_response(register)

            else:
                def reg_fun(self, data=None):
                    self.send_command(register, data, signed=signed)
                    return self.get_response(register)

            reg_fun.__doc__ = description
            reg_fun.__name__ = fnname
            return reg_fun

        for register_file in register_files:
            register_file = resource_filename('itla',
                                              'registers/' + register_file)
            with open(register_file, 'r') as register_yaml:
                register_spec = yaml.safe_load(register_yaml)

                for register_name in register_spec:
                    register_data = register_spec[register_name]
                    setattr(ITLABase,
                            '_' + register_data['fnname'],
                            mkfn(**register_data))

    def __enter__(self):
        """TODO describe function

        :returns:

        """
        self.connect()

    def __exit__(self, exc_type, exc_value, traceback):
        """TODO describe function

        :param exc_type:
        :param exc_value:
        :param traceback:
        :returns:

        """
        self.disconnect()

    def __del__(self):
        """TODO describe function

        :returns:

        """
        if self._device is not None:
            self.disconnect()

    def connect(self):
        """Establishes a serial connection with the port provided

        **For some reason on Linux opening the serial port causes some
        power output from the laser before it has been activated. This behavior
        does not occur on Windows.**

        """
        try:
            self._device = serial.Serial(self._port, self._baudrate,
                                         timeout=self._timeout)
        except SerialException:
            raise SerialException("Connection to "
                                  + self._port + " unsuccessful.")

    def disconnect(self, leave_on=False):
        """Ends the serial connection to the laser

        :param leave_on:
        :returns:

        """
        if not self._device.is_open:
            return

        if not leave_on:
            self.disable()

        try:
            self._device.close()
        except AttributeError:
            # When does this error occur?
            # There are a few ways disconnect can be called.
            # 1) It can be called purposefully.
            # 2) It can be called by ending a `with` (ie __exit__)
            # 3) It can be called by exiting a repl or a script ending (ie. __del__).
            pass

    def send_command(self, register, data=None, signed=False):
        """Sends commands to a device.
        This function takes the hexstring, turns it into a bytestring,
        and writes it to the device.
        This function should probably be hidden from the user.

        :param device: Should be a Serial object that you can write to.
        :param hexstring: a hexstring to send to the device
        :returns: nothing
        """

        write = (data is not None)

        # convert to register to a bytestring
        register_bytes = register.to_bytes(1, 'big')

        # convert data to bytestring
        if write:
            data_bytes = data.to_bytes(2, 'big', signed=signed)

        else:
            data_bytes = (0).to_bytes(2, 'big')

        # compute the checksum
        checksum = compute_checksum(
            (write.to_bytes(1, 'big') + register_bytes + data_bytes).hex()
        )

        # compute and convery header to bytestring
        header = checksum * 16 + write
        header_bytes = header.to_bytes(1, 'big')

        # form full command and send.
        command = header_bytes + register_bytes + data_bytes
        self._device.write(command)

    def get_response(self, register):
        """This function should read from self._device. This should be called

        :param register:
        :returns: ???

        """
        # read four bytes
        response = self._device.read(4)

        print(f'response: {response.hex()}')

        # get the checksum and ... check it.
        checksum = int(response.hex()[0], 16)
        computed_checksum = compute_checksum(response.hex())

        if computed_checksum != checksum:
            raise Exception(f'Communication error expected {checksum} got '
                            + f'{computed_checksum}')

        status = int(f'{response[0]:08b}'[-2:], 2)
        print(f'status: {status}')

        try:
            raise self._response_status[status]

        except TypeError:
            # a type error occurs if we try to raise "OK"
            # in this situation we should just pass.
            pass

        except AEAException:
            response = self.read_aea()
            return response

        if register != response[1]:
            raise Exception('The returned register does not match '
                            + 'the register sent to the device. '
                            + f'Got {response[1]} expected {register}.')

        return response[2:]

    def upgrade_firmware(self, firmware_file):
        """ This function should update the firmware for the laser.
        """

        # STEPS:
        # 1) release
        # 2) set baudrate to 115200
        # 3) disconnect and reconnect at update baudrate
        # 4) send dlconfig signal
        # 5) ????
        # 6) profit
        raise Warning("this is not implemented yet.")


class ITLA():
    '''
    The class that users should interface and create ITLA objects from.
    Basically just used to select the appropriate subclass of ITLABase.
    '''

    def __new__(cls, *args, version='1.3', **kwargs):
        '''
        this function is executed on initialization of an object before
        __init__ here we divert the initialization process to initialize
        one of the subclasses of ITLABase.

        I would love it if there were a way to make everything a
        subclass of ITLA and merge the ITLA and ITLABase classes.
        This would streamline some things and make it easier to do type
        checking since it only makes sense that all ITLA laser objects would
        be subclasses of ITLA not some random arbitrary ITLABase.

        The current issue in doing this is that we end up with a circular
        import I think.
        '''
        from .itla12 import ITLA12
        from .itla13 import ITLA13

        class_dict = {
            '1.3': ITLA13,
            '1.2': ITLA12,
        }

        return class_dict[version](*args, **kwargs)
