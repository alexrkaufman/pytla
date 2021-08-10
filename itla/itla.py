from time import sleep
import yaml
import serial
from scipy.constants import speed_of_light
from serial.serialutil import SerialException
from pkg_resources import resource_filename
from .itla_errors import *
from .utils import (setup_registers, form_packet,
                    compute_checksum)


regdoc = '**Uses register {register:#04X}.**\n\n'


class ITLA():
    '''
    A class that represents the an ITLA
    and exposes a user friendly API for controlling functionality.

    OIF-ITLA-MSA-01.3 is the standard implemented here.
    Certain functions such as set_frequency() dont fully implement this yet
    because I dont know how to do checks to see if the optional FCF3
    functions are implemented for a particular laser.

    Things to figure out

      * What should be exposed to the user?
      * Can we abstract away the concept of registers and stuff
        in here so you don't have to deal with it.

   There are some functions that could be implemented like set_fatalstatus.
   I think this is probably a bad idea even though it isnt write only.

   Set Frequency is my platonic ideal for the higher level functions.

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

        register_files = ['registers_itla.yaml', *register_files]

        # this function creates register functions
        def mkfn(*, fnname, register, description, readonly, signed, AEA):
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
                    setattr(ITLA,
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
            raise SerialException("Connection to " + self._port + " unsuccessful.")

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

    def nop(self, data=None):
        """TODO describe function

        :param data:
        :returns:

        """
        # pretty sure the data does nothing
        if data is not None:
            response = self._nop(data)
        else:
            response = self._nop()

        error_field = int(response.hex()[-1], 16)
        if bool(error_field):
            raise self._nop_errors[error_field]

    def enable(self):
        """TODO describe function

        :returns:

        """
        # I'm writing this out partially for transparency
        # Maybe unnecessary or non-optimal
        data = [0] * 16
        # bit 3 SENA bit
        data[3] = 1
        data = int(''.join(str(x) for x in data[::-1]), 2)

        try:
            self._resena(data)
        except CPException:
            print('Waiting for laser to power on and stabilize.')
            # This would be a good place for a waiting function


    def disable(self):
        """TODO describe function

        :returns:

        """
        # set SENA bit (bit 3) to zero
        data = [0] * 16
        data = int(''.join(str(x) for x in data[::-1]), 2)
        self._resena(data)

    def hard_reset(self):
        """TODO describe function

        :returns:

        """
        # I'm writing this out partially for transparency
        # Maybe unnecessary or non-optimal
        data = [0] * 16
        # bit 0: Module Reset
        data[0] = 1
        data = int(''.join(str(x) for x in data[::-1]), 2)

        self._resena(data)

    def soft_reset(self):
        """TODO describe function

        :returns:

        """
        # I'm writing this out partially for transparency
        # Maybe unnecessary or non-optimal
        data = [0] * 16
        # bit 1: Soft Reset
        data[1] = 1
        data = int(''.join(str(x) for x in data[::-1]), 2)

        self._resena(data)

    def get_device_type(self):
        """
        returns a string containing the device type.
        """
        response_bytes = self._devtyp()

        return response_bytes.decode('utf-8')

    def get_manufacturer(self):
        """
        Return's a string containing the manufacturer's name.
        """
        response_bytes = self._mfgr()

        return response_bytes.decode('utf-8')

    def get_model(self):
        """
        return's the model as a string
        """
        response_bytes = self._model()

        return response_bytes.decode('utf-8')

    def get_serialnumber(self):
        """
        returns the serial number
        """
        response_bytes = self._serno()

        return response_bytes.decode('utf-8')

    def get_manufacturing_date(self):
        """returns the manufacturing date"""
        response_bytes = self._mfgdate()

        return response_bytes.decode('utf-8')

    def get_firmware_release(self):
        """
        returns a manufacturer specific firmware release
        """
        response_bytes = self._release()

        return response_bytes.decode('utf-8')

    def get_backwardscompatibility(self):
        """
        returns a manufacturer specific firmware backwards compatibility
        as a null terminated string
        """
        response_bytes = self._relback()

        return response_bytes.decode('utf-8')

    def read_aea(self):
        """
        reads the AEA register data until an execution error is thrown.
        """
        aea_response = b''
        try:
            while True:
                aea_response += self._aea_ear()

        except ExecutionError as ee:

            try:
                self.nop()

            except EREError as eree:
                # If this throws an ERE error then we have completed reading AEA
                pass

            except NOPException as nop_e:
                raise nop_e

        return aea_response

    def set_power(self, pwr_dBm):
        """Sets the power of the ITLA laser. Units of dBm.

        :param pwr_dBm: The power setting for the laser in dBm. Has precision XX.XX.
        :returns: None

        """
        try:
            self._pwr(int(pwr_dBm * 100))

        except ExecutionError:

            try:
                self.nop()

            except RVEError as rvee:
                print("The provided power " + str(pwr_dBm)
                      + " is outside of the range for this device.")
                print("The power is currently set to: "
                      + str(self.get_power_setting()))
                raise rvee

    def get_power_setting(self):
        """Gets current power setting set by set_power. Should be in dBm.

        :returns:

        """
        # Gets power setting, not actual optical output power.
        response = self._pwr()
        return int.from_bytes(response, 'big', signed=True) / 100

    def get_power_output(self):
        """Gets the actual optical output power of the laser.
        Only an approximation, apparently. Units dBm.

        :returns:

        """
        response = self._oop()

        return int.from_bytes(response, 'big', signed=True) / 100

    def get_power_min(self):
        """Gets the minimum optical power output of the module. Units dBm.

        :returns:

        """
        response = self._opsl()
        return int.from_bytes(response, 'big', signed=True) / 100

    def get_power_max(self):
        """Gets the maximum optical power output of the module. Units dBm.

        :returns:

        """
        response = self._opsh()
        return int.from_bytes(response, 'big', signed=True) / 100

    def set_fcf(self, freq):
        '''
        This sets the first channel frequency.
        It does not reset the channel so this frequency will only be equal
        to the output frequency if channel=1.

        '''
        # convert frequency to MHz
        freq = int(freq * 1e6)

        freq_str = str(freq)
        fcf1 = int(freq_str[0:3])
        fcf2 = int(freq_str[3:7])
        fcf3 = int(freq_str[7:])

        try:
            # is it better to split these into their own try/except blocks?
            self._fcf1(fcf1)
            self._fcf2(fcf2)
            self._fcf3(fcf3)

        except ExecutionError:
            try:
                self.nop()
            except RVEError as error:
                print(int(fcf1) + 'THz is out of bounds for this laser. ')
                print('The frequency must be within the range, '
                      + self.get_frequency_min() + ' - '
                      + self.get_frequency_max() + ' THz.')
                raise error from None

            except CIEError as error:
                print("You cannot change the first channel frequency "
                      + "while the laser is enabled.")
                print('The current frequency is: ' + self.get_frequency() + ' THz')
                raise error from None

    def set_frequency(self, freq):
        """Sets the frequency of the laser in TerraHertz.

        Has MHz resolution. Will round down.

        This function sets the first channel frequency and then sets the
        channel to 1 so that the frequency output when the laser is enabled
        will be the frequency given to this function.

        If you would like to only change the first channel frequency use
        the function `set_fcf`.

        :param freq: The desired frequency setting in THz.
        :returns: None

        """

        self.set_fcf(freq)
        self.set_channel(1)

        # This does a check so this only runs if fine tuning has been turned on.
        if self.get_fine_tuning() != 0:

            # There needs to be some delay between this and setting channel.
            # even with some delay the CII error occurs from time to time. Fix.
            # This delay is way longer than i would like.
            # It would be ideal to have no sleeping necessary conditions.
            sleep(1)
            try:
                self.set_fine_tuning(0)

            except ExecutionError as ee:

                try:
                    self.nop()

                except NOPException as nop_e:
                    raise nop_e

                except CPException as cpe:
                    print('Fine tuning takes some time. Waiting 5s.')
                    sleep(5)

    def get_fcf(self):
        """ Get the currently set first channel frequency.
        """
        response = self._fcf1()
        fcf1 = int.from_bytes(response, 'big')

        response = self._fcf2()
        fcf2 = int.from_bytes(response, 'big')

        response = self._fcf3()
        fcf3 = int.from_bytes(response, 'big')

        return fcf1 + fcf2 * 1e-4 + fcf3 * 1e-6

    def get_frequency(self):
        """gets the current laser operating frequency with channels
        and everything accounted for.

        :returns:

        """
        response = self._lf1()
        lf1 = int.from_bytes(response, 'big')

        response = self._lf2()
        lf2 = int.from_bytes(response, 'big')

        response = self._lf3()
        lf3 = int.from_bytes(response, 'big')

        return lf1 + lf2 * 1e-4 + lf3 * 1e-6

    def set_wavelength(self, wvl):
        """Set the wavelength in nm. Converts wavelength to freq and calls set_frequency.

        :param wvl: The desired wavelength in nm.

        """
        freq = (speed_of_light / (wvl * 1e-9)) * 1e-12  # get frequency in THz
        self.set_frequency(freq)
        raise Warning('There seems to be some roundoff error here. best to avoid this for now.')

    def dither_enable(self, waveform='sinusoidal'):
        """
        """
        if (waveform.lower() != 'sinusoid'
            or waveform.lower() != 'triangular'
              or waveform.lower() != 'sin' or waveform.lower() != 'tri'):

            raise ValueError('waveform must be \'sinusoidal\', or \'triangular\'')

        data = [0] * 16
        # bit 1 Digital Dither Enable bit
        data[1] = 1
        data = int(''.join(str(x) for x in data[::-1]), 2)

        try:
            self._dithere(data)
        except CPException:
            print('enabling dither')

    def dither_disable(self):
        """
        disables digital dither
        """
        #i think that we should try to preserve other bits rather than setting all
        #data to zero across the board
        data = [0] * 16
        data = int(''.join(str(x) for x in data[::-1]), 2)
        self._dithere(data)

    def set_dither_rate(self, rate):
        """
        set dither rate in kHz, utilizes DitherR register
        :param rate: an unsigned short integer specifying dither rate in kHz
        """
        self._ditherr(rate)

    def get_dither_rate(self):
        """
        get dither rate, utilizes DitherR register
        """
        response = self._ditherr()
        return int.from_bytes(response, 'big')

    def set_dither_frequency(self, rate):
        """
        set dither modulation frequency, utilizes DitherF register
        :param rate: an unsigned short integer encoded as the FM peak-to-peak frequency
        deviation as Ghz*10
        """
        self._ditherf(rate)

    def get_dither_frequency(self):
        """
        get dither modulation frequency, utilizes DitherF register
        """
        response = self._ditherf()
        return int.from_bytes(response, 'big')

    def set_dither_amplitude(self, amplitude):
        """
        set dither modulation amplitude, utilizes DitherA register
        :param amplitude: an unsigned short integer encoded as the AM peak-to-peak amplitude
        deviation as 10*percentage of the optical power
        """
        self._dithera(amplitude)

    def get_dither_amplitude(self):
        """
        get dither modulation amplitude, utilizes DitherA register
        """
        response = self._dithera()
        return int.from_bytes(response, 'big')

    def get_wavelength(self):
        """TODO describe function

        :returns:

        """
        raise Warning("this is not implemented yet.")

    def get_output_wavelength(self):
        """TODO describe function

        :returns:

        """
        raise Warning("this is not implemented yet.")

    def get_temp(self):
        """TODO describe function

        :returns:

        """
        response = self._ctemp()
        temp_100 = int.from_bytes(response, 'big')

        return temp_100 / 100

    def get_frequency_min(self):
        """command to read minimum frequency supported by the module

        :returns:

        """
        response = self._lfl1()
        lfl1 = int.from_bytes(response, 'big')

        response = self._lfl2()
        lfl2 = int.from_bytes(response, 'big')

        response = self._lfl3()
        lfl3 = int.from_bytes(response, 'big')

        return lfl1 + lfl2 * 1e-4 + lfl3 * 1e-6

    def get_frequency_max(self):
        """command to read maximum frequency supported by the module

        :returns:

        """
        response = self._lfh1()
        fcf1 = int.from_bytes(response, 'big')

        response = self._lfh2()
        fcf2 = int.from_bytes(response, 'big')

        response = self._lfh3()
        fcf3 = int.from_bytes(response, 'big')

        return fcf1 + fcf2 * 1e-4 + fcf3 * 1e-6

    def get_grid_min(self):
        """TODO describe function

        :returns:

        """
        try:
            self._lgrid()
            freq_lgrid = int(self._response[4:], 16)

            self._lgrid2()
            freq_lgrid2 = int(self._response[4:], 16)

        except ExecutionError as ee:
            self.nop()

        return freq_lgrid * 1e-1 + freq_lgrid2 * 1e-3

    def set_grid(self, grid_freq):
        """Set the grid spacing in GHz.

        MHz resolution.

        :param grid_freq: the grid frequency spacing in GHz
        :returns:

        """
        grid_freq = str(int(grid_freq * 1000))
        data = int(grid_freq[0:4])
        data_2 = int(grid_freq[4:])

        self._grid(data)
        self._grid2(data_2)

    def get_grid(self):
        """get the grid spacing in GHz

        :returns: The grid spacing in GHz.

        """
        response = self._grid()
        grid_freq = int.from_bytes(response, 'big', signed=True)

        response = self._grid2()
        grid2_freq = int.from_bytes(response, 'big', signed=True)

        return grid_freq * 1e-1 + grid2_freq * 1e-3

    def get_age(self):
        """TODO describe function

        :returns:

        """
        response = self._age()
        age = int.from_bytes(response, 'big')

        return f'Age: {age} / 100%'

    def set_channel(self, channel):
        """TODO describe function

        :param channel:
        :returns:

        """
        # check type and stuff
        if not isinstance(channel, int):
            raise TypeError("Channel must be an integer")
        if channel < 0:
            raise ValueError("Channel must be positive.")
        if channel > 0xFFFFFFFF:
            raise ValueError("Channel must be a 32 bit integer (<=0xFFFFFFFF).")

        # Split the channel choice into two options.
        channel_hex = f'{channel:08x}'

        channell = int(channel_hex[4:], 16)
        channelh = int(channel_hex[0:4], 16)

        # Set the channel registers.
        self._channel(channell)
        self._channelh(channelh)

    def get_channel(self):
        """TODO describe function

        :returns:

        """
        # This concatenates the data bytestrings
        response = self._channelh() + self._channel()

        channel = int.from_bytes(response, 'big')

        return channel

    def set_fine_tuning(self, ftf):
        """
        This function provides off grid tuning for the laser's frequency.
        The adjustment applies to all channels uniformly.
        This is typically used after the laser if locked and minor adjustments
        are required to the frequency.

        The command may be pending in the event that the laser output is
        enabled. The pending bit is cleared once the fine tune frequency
        has been achieved.

        **???** It seems like this can be done with the laser running.

        :param ftf: The fine tune frequency adjustment in GHz
        """

        ftf = int(ftf * 1e3)

        # We will leave this bare. This way the user can set and handle
        # their own timing and check to make sure the laser has reached the
        # desired fine tuning frequency.
        # It WILL throw a "pending" error if the laser is on when setting.
        self._ftf(ftf)

    def get_fine_tuning(self):
        """
        This function returns the setting for the
        off grid tuning for the laser's frequency.

        :return ftf: The fine tune frequency adjustment in GHz
        """

        response = self._ftf()
        ftf = int.from_bytes(response, 'big', signed=True)

        return ftf * 1e-3

    def get_temps(self):
        '''
        Returns a list of currents in degrees Celcius.
        In the following order:

        Technology 1: [Diode Temp, Case Temp]
        '''
        # get response this should be a long byte string
        response = self._temps()

        data = [int.from_bytes(response[i: i+2], 'big', signed=True) / 10
                for i in range(0, len(response), 2)]

        return data

    def get_currents(self):
        '''
        Returns a list of currents in mA.
        In the following order:

        Technology 1: [TEC, Diode]
        Technology 2: [TED, Diode 1, Diode 2, Diode 3, Diode 4, SOA]
        Technology 3: [TEC, Diode 1, tbd, tbd, tbd, ...]
        '''
        # get response this should be a long byte string
        response = self._currents()

        data = [int.from_bytes(response[i: i+2], 'big', signed=True) / 10
                for i in range(0, len(response), 2)]

        return data


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

    def get_last_response(self):
        '''This function gets the most recent response sent from the laser.
        The response is parsed for errors and stuff the way any normal response
        would be. The variable `self._response` is set to the last response again.

        I dont know why you would need to do this.
        '''
        return self._lstresp()

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
    def get_error_fatal(self, reset=False):
        """
        reads fatal error register statusf and checks each bit against the
        fatal error table to determine the fault
        
        :param reset: resets/clears latching errors 

        """
        response = self._statusf()
        statusf = int.from_bytes(response, 'big')
        statusf = f'{statusf:016b}'
        status_array = [int(code) for code in statusf]
        status_array.reverse()
        print(status_array)

        if any(status_array):
            print("Current Status Fatal Error")

            if status_array[0] == 1:
                print("FPWRL")
            if status_array[1] == 1:
                print("FTHERML")
            if status_array[2] == 1:
                print("FFREQL")
            if status_array[3] == 1:
                print("FVSFL")
            if status_array[4] == 1:
                print("CRL")
            if status_array[5] == 1:
                print("MRL")
            if status_array[6] == 1:
                print("CEL")
            if status_array[7] == 1:
                print("XEL")
            if status_array[8] == 1:
                print("FPWR")
            if status_array[9] == 1:
                print("FTHERM")
            if status_array[10] == 1:
                print("FFREQ")
            if status_array[11] == 1:
                print("FVSF")
            if status_array[12] == 1:
                print("DIS")
            if status_array[13] == 1:
                print("FATAL")
            if status_array[14] == 1:
                print("ALM")
            if status_array[15] == 1:
                print("SRQ ")
            if reset == True:
                data_reset = [0] * 16
                data_reset = int(''.join(str(x) for x in data_reset[::-1]), 2)
                self._statusf(data_reset)
                
    def get_error_warning(self, reset=False):
        """
        reads warning error register statusw and checks each bit against the
        warning error table to determine the fault

        If the laser is off then some of the latched warnings will be set on.
        
        :param reset: resets/clears latching errors 
        """
        response = self._statusw()
        statusw = int.from_bytes(response, 'big')
        statusw = f'{statusw:016b}'
        status_array = [int(code) for code in statusw]
        status_array.reverse()
        print(status_array)

        if any(status_array):
            print("Current Status Warning Error")

            if status_array[0] == 1:
                print("WPWRL")
            if status_array[1] == 1:
                print("WTHERML")
            if status_array[2] == 1:
                print("WFREQL")
            if status_array[3] == 1:
                print("WVSFL")
            if status_array[4] == 1:
                print("CRL")
            if status_array[5] == 1:
                print("MRL")
            if status_array[6] == 1:
                print("CEL")
            if status_array[7] == 1:
                print("XEL")
            if status_array[8] == 1:
                print("WPWR")
            if status_array[9] == 1:
                print("WTHERM")
            if status_array[10] == 1:
                print("WFREQ")
            if status_array[11] == 1:
                print("FVSF")
            if status_array[12] == 1:
                print("DIS")
            if status_array[13] == 1:
                print("FATAL")
            if status_array[14] == 1:
                print("ALM")
            if status_array[15] == 1:
                print("SRQ ")
            if reset == True:
                data_reset = int('00ff', 16)
                self._statusw(data_reset)
                
    
    def get_fatal_power_thresh(self):
        """
        reads maximum plus/minus power deviation in dB for which the fatal alarm is asserted
        
        """
        response = self._fpowth()
        pow_fatal = int.from_bytes(response, 'big') / 100 
        #correcting for proper order of magnitude
        return pow_fatal
        
    def get_warning_power_thresh(self):
        """
        reads maximum plus/minus power deviation in dB for which the warning alarm is asserted
        
        """
        response = self._wpowth()
        pow_warn = int.from_bytes(response, 'big') / 100 
        #correcting for proper order of magnitude
        return pow_warn
    
    def get_fatal_freq_thresh(self):
        """
        reads maximum plus/minus frequency deviation in GHz for which the fatal alarm is asserted
        
        """
        response = self._ffreqth()
        freq_fatal = int.from_bytes(response, 'big') / 10 
        #correcting for proper order of magnitude
        response2 = self._ffreqth2()
        freq_fatal2 = int.from_bytes(response2, 'big') / 100
        #get frequency deviation in MHz and add to GHz value
        return freq_fatal + freq_fatal2
        
    
    def get_warning_freq_thresh(self):
        """
        reads maximum plus/minus frequency deviation in GHz for which the warning alarm is asserted
        
        """
        response = self._wfreqth()
        freq_warn = int.from_bytes(response, 'big') / 10 
        #correcting for proper order of magnitude
        response2 = self._wfreqth2()
        freq_warn2 = int.from_bytes(response2, 'big') / 100
        #get frequency deviation in MHz and add to GHz value
        return freq_warn + freq_warn2


    def get_fatal_therm_thresh(self):
        """
        reads maximum plus/minus thermal deviation in degree celcius for which the fatal alarm is asserted
        
        """
        response = self._fthermth()
        therm_fatal = int.from_bytes(response, 'big') / 100 
        #correcting for proper order of magnitude
        return therm_fatal
        
    def get_warning_therm_thresh(self):
        """
        reads maximum plus/minus thermal deviation in degree celcius for which the warning alarm is asserted
        """
        response = self._wthermth()
        therm_thresh = int.from_bytes(response, 'big') / 100 
        #correcting for proper order of magnitude
        return therm_thresh
        
    def get_srq_trigger(self):
        """
        Utilizes SRQT register to identify why SRQ was asserted in StatusF and StatusW registers 
        
        """
        response = self._srqt()
        status = int.from_bytes(response, 'big')
        status = f'{status:016b}'
        status_array = [int(code) for code in status]
        status_array.reverse()
        print(status_array)

        if any(status_array):
            print("SRQ Status: Asserted")

            if status_array[0] == 1:
                print("FPWRL")
            if status_array[1] == 1:
                print("FTHERML")
            if status_array[2] == 1:
                print("FFREQL")
            if status_array[3] == 1:
                print("FVSFL")
            if status_array[4] == 1:
                print("CRL")
            if status_array[5] == 1:
                print("MRL")
            if status_array[6] == 1:
                print("CEL")
            if status_array[7] == 1:
                print("XEL")
            if status_array[8] == 1:
                print("WPWRL")
            if status_array[9] == 1:
                print("WTHERML")
            if status_array[10] == 1:
                print("WFREQL")
            if status_array[11] == 1:
                print("WVSFL")
            if status_array[12] == 1:
                print("DIS")
            if status_array[13] == 1:
                print("NONE")
            if status_array[14] == 1:
                print("NONE")
            if status_array[15] == 1:
                print("NONE")
                
    def get_fatal_trigger(self):
            """
            Utilizes FatalT register to identify which fatal conditon was asserted in StatusF and StatusW registers 
            
            """
            response = self._fatalt()
            status = int.from_bytes(response, 'big')
            status = f'{status:016b}'
            status_array = [int(code) for code in status]
            status_array.reverse()
            print(status_array)

            if any(status_array):
                print("SRQ Status: Asserted")

                if status_array[0] == 1:
                    print("FPWRL")
                if status_array[1] == 1:
                    print("FTHERML")
                if status_array[2] == 1:
                    print("FFREQL")
                if status_array[3] == 1:
                    print("FVSFL")
                if status_array[4] == 1:
                    print("NONE")
                if status_array[5] == 1:
                    print("MRL")
                if status_array[6] == 1:
                    print("NONE")
                if status_array[7] == 1:
                    print("NONE")
                if status_array[8] == 1:
                    print("WPWRL")
                if status_array[9] == 1:
                    print("WTHERML")
                if status_array[10] == 1:
                    print("WFREQL")
                if status_array[11] == 1:
                    print("WVSFL")
                if status_array[12] == 1:
                    print("NONE")
                if status_array[13] == 1:
                    print("NONE")
                if status_array[14] == 1:
                    print("NONE")
                if status_array[15] == 1:
                    print("NONE")

    def get_alm_trigger(self):
            """
            Utilizes ALMT register to identify why ALM was asserted in StatusF and StatusW registers 
            
            """
            response = self._almt()
            status = int.from_bytes(response, 'big')
            status = f'{status:016b}'
            status_array = [int(code) for code in status]
            status_array.reverse()
            print(status_array)

            if any(status_array):
                print("SRQ Status: Asserted")

                if status_array[0] == 1:
                    print("FPWR")
                if status_array[1] == 1:
                    print("FTHERM")
                if status_array[2] == 1:
                    print("FFREQ")
                if status_array[3] == 1:
                    print("FVSF")
                if status_array[4] == 1:
                    print("NONE")
                if status_array[5] == 1:
                    print("NONE")
                if status_array[6] == 1:
                    print("NONE")
                if status_array[7] == 1:
                    print("NONE")
                if status_array[8] == 1:
                    print("WPWR")
                if status_array[9] == 1:
                    print("WTHERM")
                if status_array[10] == 1:
                    print("WFREQ")
                if status_array[11] == 1:
                    print("WVSF")
                if status_array[12] == 1:
                    print("NONE")
                if status_array[13] == 1:
                    print("NONE")
                if status_array[14] == 1:
                    print("NONE")
                if status_array[15] == 1:
                    print("NONE")             

