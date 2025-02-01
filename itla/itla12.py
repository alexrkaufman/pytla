from time import sleep

from . import logger
from .itla import ITLABase
from .itla_errors import (
    CIEError,
    CPException,
    EREError,
    ExecutionError,
    NOPException,
    RVEError,
)
from .itla_status import (
    MCB,
    AlarmTrigger,
    FatalError,
    FatalTrigger,
    Resena,
    SQRTrigger,
    WarningError,
    Waveform,
)


class ITLA12(ITLABase):
    """
    A class that represents the ITLA12
    and exposes a user friendly API for controlling functionality.

    Things to figure out

    * What should be exposed to the user?
    * Can we abstract away the concept of registers and stuff
        in here so you don't have to deal with it.

    There are some functions that could be implemented like set_fatalstatus.
    I think this is probably a bad idea even though it isnt write only.

    Set Frequency is my platonic ideal for the higher level functions.

    """

    def __init__(
        self, serial_port, baudrate, timeout=0.5, register_files=None, sleep_time=0.1
    ):
        """Initializes the ITLA12 object.

        :param serial_port: The serial port to connect to.
        Can either be linux/mac type such as '/dev/ttyUSBX' or windows type 'comX'
        :param baudrate: The baudrate for communication. I have primarily seen
        lasers using 9600 as the default and then higher for firmware upgrades.
        This may be laser specific.
        :param timeout: How long should we wait to receive a response from the laser
        :param register_files: Any additional register files you would like to include
        beyond the default MSA-01.2 defined registers. These must be in a yaml format as
        described in the project's README.
        :param sleep_time: time in seconds. Used in wait function
        """
        if register_files is None:
            register_files = []

        register_files = ["registers_itla12.yaml", *register_files]

        self.sleep_time = sleep_time

        super().__init__(
            serial_port, baudrate, timeout=timeout, register_files=register_files
        )

    def nop(self, data=None):
        """The No-Op operation.

        This is a good test to see if your laser is communicating properly.
        It should read 0000 data or echo whatever data you send it if you send it something.
        The data you write to nop gets overwritten as soon as you read it back.

        `nop()` also returns more informative errors following an ExecutionError.
        This is not called by default so you must do this explicitly if you want
        to see more informative error information.

        See 9.4.1 NOP/Status (ResEna 0x00) [RW] in OIF-ITLA-MSA.

        :param data: Data to write

        :returns: None
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
        """Enables laser optical output.
        There is a time delay after execution of this function to
        proper stable laser output.

        See 9.6.3 Reset/Enable (ResEna 0x32) [RW]

        :returns: None
        """
        # I'm writing this out partially for transparency
        # Maybe unnecessary or non-optimal
        self._resena(Resena.SENA)

    def disable(self):
        """disables the laser

        See 9.6.3 Reset/Enable (ResEna 0x32) [RW]

        :returns: None
        """
        self._resena(0)

    def hard_reset(self):
        """initiate module reset

        The hardware reset is typically traffic interrupting since it will reset
        control loops as well. The host can poll the communication’s interface
        waiting for a response packet indicating that the interface is ready to
        communicate. Note that a response is returned to acknowledge the reset
        request before the reset is started

        The impact to the optical signal is undefined. This bit is self clearing.

        See 9.6.3 Reset/Enable (ResEna 0x32) [RW]

        :returns: None
        """
        self._resena(Resena.MR)

    def soft_reset(self):
        """initiate soft reset

        The soft reset resets the communication’s interface and is traffic
        non-interrupting. Extended address registers are reset.

        See 9.6.3 Reset/Enable (ResEna 0x32) [RW]

        :returns: None
        """
        self._resena(Resena.SR)

    def get_reset_enable(self):
        """return ResEna register.

        See 9.6.3 Reset/Enable (ResEna 0x32) [RW]
        """
        response = self._resena()
        return Resena(int.from_bytes(response, "big"))

    def set_alarm_during_tuning(self):
        """Set alarm during tuning
        mcb(ADT)

        See 9.6.4 Module Configuration Behavior (MCB 0x33) [RW]
        """
        self._mcb(MCB.ADT)

    def set_shutdown_on_fatal(self):
        """Set shutdown on fatal.
        mcb(SDF)

        See 9.6.4 Module Configuration Behavior (MCB 0x33) [RW]
        """
        self._mcb(MCB.SDF)

    def get_configuration_behavior(self):
        """
        Return MCB register.

        See 9.6.4 Module Configuration Behavior (MCB 0x33) [RW]
        """
        response = self._mcb()
        return MCB(int.from_bytes(response, "big"))

    def is_disabled(self):
        """
        Return if disabled.

        See 9.6.3 Reset/Enable (ResEna 0x32) [RW] in OIF-ITLA-MSI.

        For some lasers, FatalError.DIS is not triggered (even if TriggerT allows it).
        Consider overwriting this methods and monitoring FatalError.ALM.
        """
        fatal_error = self.get_error_fatal()
        fatal_trigger = self.get_fatal_trigger()
        resena = self.get_reset_enable()
        mcb = self.get_configuration_behavior()

        sdf = MCB.SDF in mcb
        sena = Resena.SENA in resena
        dis = FatalError.DIS in fatal_error

        return ((fatal_error & fatal_trigger) and sdf) or (not sena) or (not dis)

    def is_enabled(self, *args):
        """
        Return if enabled.  See is_disabled.
        """
        return not self.is_disabled(*args)

    def get_device_type(self):
        """returns a string containing the device type

        DevTyp returns the module’s device type. For all tunable lasers covered by this MSA, the
        module will return the null terminated string “CW ITLA\0” (eight bytes including the
        terminating null character) indirectly through the AEA mechanism. The device type register
        is provided such that a host can distinguish between different types of tunable devices.type.

        See 9.4.2 Device Type (DevTyp 0x01) [R]
        """
        response_bytes = self._devtyp()

        return response_bytes.decode("utf-8")

    def get_manufacturer(self):
        """returns a string containing the manufacturer's name.

        MFGR returns the module’s manufacturers ID null terminated string indirectly through the
        AEA mechanism

        See 9.4.3 Manufacturer (MFGR 0x02) [R]
        """
        response_bytes = self._mfgr()

        return response_bytes.decode("utf-8")

    def get_model(self):
        """returns the model as a string

        Model returns the module’s model designation string indirectly through the AEA
        mechanism. The null terminated string containing the module’s model designation is
        placed into a field of not more than 80 bytes in size. The model string is defined by the
        manufacturer

        See 9.4.4 Model (Model 0x03) [R]
        """
        response_bytes = self._model()

        return response_bytes.decode("utf-8")

    def get_serialnumber(self):
        """returns the serial number

        SerNo returns the module’s serial number string indirectly through the AEA mechanism.
        The null terminated string containing the module’s serial number is placed into a field of not
        more than 80 bytes in size. The serial number string is defined by the manufacturer.

        See 9.4.5 Serial Number (SerNo 0x04) [R]
        """
        response_bytes = self._serno()

        return response_bytes.decode("utf-8")

    def get_manufacturing_date(self):
        """returns the manufacturing date

        MFGDate returns the manufacturing date string of the module indirectly through the AEA
        mechanism. The null terminated string containing the date string is contained in a field
        size of 12 bytes.

        See 9.4.5 Manufaturing Date (MFGDate 0x05) [R]
        """
        response_bytes = self._mfgdate()

        return response_bytes.decode("utf-8")

    def get_firmware_release(self):
        """returns a manufacturer specific firmware release

        Release returns the release string of the module indirectly through the AEA mechanism.
        The null terminated string containing the module release information is placed into a field of
        not more than 80 bytes in size. Note that a module may have one or more firmware and/or
        hardware revisions to track. The release field also encodes the application space
        identifier.

        See 9.4.7 Release (Release 0x06) [R]
        """
        response_bytes = self._release()

        return response_bytes.decode("utf-8")

    def get_backwardscompatibility(self):
        """returns a manufacturer specific firmware backwards compatibility
        as a null terminated string

        RelBack returns the release backwards compatibility string of the module indirectly through
        the AEA mechanism. The null terminated string containing the earliest release string which
        is fully backwards compatible with the current module. The string is contained in a field of
        not more than 80 bytes in size. Note that a module may have one or more firmware and/or
        hardware revisions to track as described in the Release (0x06) register

        See 9.4.8 Release Backwards Compatibility (RelBack 0x07) [R]
        """
        response_bytes = self._relback()

        return response_bytes.decode("utf-8")

    def read_aea(self):
        """reads the AEA register data until an execution error is thrown.

        See 9.4.11 Extended Addressing Mode Registers (0x09-0x0B, 0x0E-0x10) [RW]
        """
        aea_response = b""
        try:
            while True:
                aea_response += self._aea_ear()

        except ExecutionError:
            try:
                self.nop()

            except EREError:
                # If this throws an ERE error then we have completed reading AEA
                pass

            except NOPException as nop_e:
                raise nop_e

        return aea_response

    def wait(self):
        """Wait until operation is complete.
        It check if the operation is completed every self.sleep_time seconds.
        """
        while True:
            try:
                self.nop()
            except CPException:
                if self.sleep_time is not None:
                    sleep(self.sleep_time)
            else:
                break

    def wait_until_enabled(self):
        """TODO: Add documentation."""
        while self.is_disabled():
            if self.sleep_time is not None:
                sleep(self.sleep_time)

    def wait_until_disabled(self):
        """TODO: Add documentation."""
        while self.is_enabled():
            if self.sleep_time is not None:
                sleep(self.sleep_time)

    def set_power(self, pwr_dBm):
        """Sets the power of the ITLA laser.
        Units of dBm.

        See 9.6.2 Optical Power Set Point (PWR 0x31) [RW]

        :param pwr_dBm: The power setting for the laser in dBm. Has precision XX.XX.
        :returns: None
        """
        try:
            self._pwr(round(pwr_dBm * 100))

        except ExecutionError:
            try:
                self.nop()

            except RVEError as error:
                logger.error(
                    "The provided power %.2f dBm is outside of the range for this device. "
                    "The power is currently set to: %.2f dBm.",
                    pwr_dBm,
                    self.get_power_setting(),
                )
                raise error

    def get_power_setting(self):
        """Gets current power setting set by set_power.
        Should be in dBm.

        See 9.6.2 Optical Power Set Point (PWR 0x31) [RW]

        :returns:
        """
        # Gets power setting, not actual optical output power.
        response = self._pwr()
        return int.from_bytes(response, "big", signed=True) / 100

    def get_power_output(self):
        """returns external optical power estimate

        See 9.6.8 Optical Output Power (OOP 0x42) [R]

        :returns: External optical power estimate in dBm
        """
        response = self._oop()

        return int.from_bytes(response, "big", signed=True) / 100

    def get_power_min(self):
        """returns minimum optical power output of the module.
        Units dBm.

        See 9.7.2 Optical Power Min/Max Set Points (OPSL, OPSH 0x50 – 0x51) [R]

        :returns: minimum optical power
        """
        response = self._opsl()
        return int.from_bytes(response, "big", signed=True) / 100

    def get_power_max(self):
        """returns maximum optical power output of the module.
        Units dBm.

        See 9.7.2 Optical Power Min/Max Set Points (OPSL, OPSH 0x50 – 0x51) [R]

        :returns: maximum optical power
        """
        response = self._opsh()
        return int.from_bytes(response, "big", signed=True) / 100

    def set_fcf(self, freq):
        """
        This sets the first channel frequency.
        It does not reset the channel so this frequency will only be equal
        to the output frequency if channel=1.

        See 9.6.6 First Channel’s Frequency (FCF1, FCF2 0x35 – 0x36) [RW]

        :returns: None
        """
        # convert frequency to MHz
        freq = round(freq * 1e6)

        freq_str = str(freq)
        fcf1 = int(freq_str[0:3])
        fcf2 = int(freq_str[3:7])

        try:
            # is it better to split these into their own try/except blocks?
            self._fcf1(fcf1)
            self._fcf2(fcf2)

        except ExecutionError:
            try:
                self.nop()
            except RVEError as error:
                logger.error(
                    "%.2f THz is out of bounds for this laser. "
                    "The frequency must be within the range %.2f - %.2f THz.",
                    fcf1,
                    self.get_frequency_min(),
                    self.get_frequency_max(),
                )
                raise error

            except CIEError as error:
                logger.error(
                    "You cannot change the first channel frequency while the laser is enabled. "
                    "The current frequency is: %.2f THz",
                    self.get_frequency(),
                )
                raise error

    def set_frequency(self, freq):
        """Sets the frequency of the laser in TeraHertz.

        Has MHz resolution. Will round down.

        This function sets the first channel frequency and then sets the
        channel to 1 so that the frequency output when the laser is enabled
        will be the frequency given to this function.

        If you would like to only change the first channel frequency use
        the function `set_fcf`.

        Disable the laser before calling this function.

        See 9.6.6 First Channel’s Frequency (FCF1, FCF2 0x35 – 0x36) [RW]

        :param freq: The desired frequency setting in THz.
        :returns: None
        """

        # This does a check so this only runs if fine tuning has been turned on.
        if self.get_fine_tuning() != 0:
            # Set the fine tuning off!
            while True:
                try:
                    self.set_fine_tuning(0)
                except ExecutionError:
                    sleep(self.sleep_time)
                except CPException:
                    self.wait()
                    break
                else:
                    break

        try:
            self.set_fcf(freq)
        except CPException:
            self.wait()

        try:
            self.set_channel(1)
        except CPException:
            self.wait()

    def get_fcf(self):
        """returns first channel frequency

        See 9.6.6 First Channel’s Frequency (FCF1, FCF2 0x35 – 0x36) [RW]

        :returns: First channel frequency in THz
        """
        response = self._fcf1()
        fcf1 = int.from_bytes(response, "big")

        response = self._fcf2()
        fcf2 = int.from_bytes(response, "big")

        return fcf1 + fcf2 * 1e-4

    def get_frequency(self):
        """gets the current laser operating frequency

        See 9.6.7 Laser Frequency (LF1, LF2 0x40 – 0x41) [R]

        :returns: Current laser frequency in THz.
        """
        response = self._lf1()
        lf1 = int.from_bytes(response, "big")

        response = self._lf2()
        lf2 = int.from_bytes(response, "big")

        return lf1 + lf2 * 1e-4

    def dither_enable(self, waveform: Waveform = Waveform.SIN):
        """enables dither

        See 9.8.3 Digital Dither (Dither(E,R,A,F) 0x59-0x5C) [RW] [Optional]

        :param waveform: specifies the dither waveform
        """

        data = (waveform << 4) | 2

        self._dithere(data)

    def dither_disable(self):
        """disables digital dither

        See 9.8.3 Digital Dither (Dither(E,R,A,F) 0x59-0x5C) [RW] [Optional]
        """
        # TODO: This should preserve the waveform setting if possible
        self._dithere(0)

    def set_dither_rate(self, rate):
        """set dither rate in kHz
        utilizes DitherR register

        See 9.8.3 Digital Dither (Dither(E,R,A,F) 0x59-0x5C) [RW] [Optional]

        :param rate: an unsigned short integer specifying dither rate in kHz
        """
        self._ditherr(rate)

    def get_dither_rate(self):
        """get dither rate
        utilizes DitherR register

        See 9.8.3 Digital Dither (Dither(E,R,A,F) 0x59-0x5C) [RW] [Optional]

        :returns: Dither rate in kHz
        """
        response = self._ditherr()
        return int.from_bytes(response, "big")

    def set_dither_frequency(self, rate):
        """set dither modulation frequency
        utilizes DitherF register

        See 9.8.3 Digital Dither (Dither(E,R,A,F) 0x59-0x5C) [RW] [Optional]

        :param rate: an unsigned short integer encoded as the FM peak-to-peak frequency
        deviation as Ghz*10
        """
        self._ditherf(rate)

    def get_dither_frequency(self):
        """get dither modulation frequency
        utilizes DitherF register

        See 9.8.3 Digital Dither (Dither(E,R,A,F) 0x59-0x5C) [RW] [Optional]

        :returns: dither modulation frequency in GHz * 10
        """
        response = self._ditherf()
        return int.from_bytes(response, "big")

    def set_dither_amplitude(self, amplitude):
        """set dither modulation amplitude
        utilizes DitherA register

        See 9.8.3 Digital Dither (Dither(E,R,A,F) 0x59-0x5C) [RW] [Optional]

        :param amplitude: an unsigned short integer encoded as the AM peak-to-peak amplitude
        deviation as 10*percentage of the optical power

        :returns: None
        """
        self._dithera(amplitude)

    def get_dither_amplitude(self):
        """get dither modulation amplitude
        utilizes DitherA register

        See 9.8.3 Digital Dither (Dither(E,R,A,F) 0x59-0x5C) [RW] [Optional]

        :returns: dither aplitude in 10ths of percents
        """
        response = self._dithera()
        return int.from_bytes(response, "big")

    def get_temp(self):
        """Returns the current primary control temperature in deg C.

        See 9.6.9 Current Temperature (CTemp 0x43) [R]

        :returns: current primary control temperature in deg C
        """
        response = self._ctemp()
        temp_100 = int.from_bytes(response, "big")

        return temp_100 / 100

    def get_frequency_min(self):
        """returns minimum frequency supported by the module

        See 9.7.3 Laser’s First/Last Frequency (LFL1/2, LFH1/2 0x52-0x55) [R]

        :returns: minimum frequency in THz
        """
        response = self._lfl1()
        lfl1 = int.from_bytes(response, "big")

        response = self._lfl2()
        lfl2 = int.from_bytes(response, "big")

        return lfl1 + lfl2 * 1e-4

    def get_frequency_max(self):
        """returns maximum frequency supported by the module

        See 9.7.3 Laser’s First/Last Frequency (LFL1/2, LFH1/2 0x52-0x55) [R]

        :returns: maximum frequency in THz
        """
        response = self._lfh1()
        fcf1 = int.from_bytes(response, "big")

        response = self._lfh2()
        fcf2 = int.from_bytes(response, "big")

        return fcf1 + fcf2 * 1e-4

    def get_grid_min(self):
        """returns minimum grid spacing of the module

        See 9.7.4 Laser’s Minimum Grid Spacing (LGrid 0x56) [R]

        :returns: The minimum grid supported by the module in GHz
        """
        try:
            freq_lgrid = int.from_bytes(self._lgrid(), "big", signed=False)

        except ExecutionError:
            self.nop()

        return freq_lgrid * 1e-1

    def set_grid(self, grid_freq):
        """Set the grid spacing in GHz.
        MHz resolution.

        See 9.6.5 Grid Spacing (Grid 0x34) [RW]

        :param grid_freq: the grid frequency spacing in GHz
        :returns:

        """
        grid_freq = str(round(grid_freq * 1000))
        data = int(grid_freq[0:4])

        self._grid(data)

    def get_grid(self):
        """get the grid spacing in GHz

        See 9.6.5 Grid Spacing (Grid 0x34) [RW]

        :returns: The grid spacing in GHz.
        """
        response = self._grid()
        grid_freq = int.from_bytes(response, "big", signed=True)

        return grid_freq * 1e-1

    def get_age(self):
        """Returns the percentage of aging of the laser.
        0% indicated a brand new laser
        100% indicates the laser should be replaces.

        See 9.8.6 Laser Age (Age 0x61) [R]

        :returns: percent aging of the laser
        """
        response = self._age()
        age = int.from_bytes(response, "big")

        return age

    def set_channel(self, channel):
        """Sets the laser's operating channel.

        MSA-01.2 lasers support a 16 bit channel value.

        This defines how many spaces along the grid
        the laser's frequency is displaced from the first channel frequency.

        See 9.6.1 Channel (Channel 0x30) [RW]

        :param channel:
        :returns: None

        """
        # check type and stuff
        if not isinstance(channel, int):
            raise TypeError("Channel must be an integer")
        if channel < 0:
            raise ValueError("Channel must be positive.")
        if channel > 0xFFFF:
            raise ValueError("Channel must be a 16 bit integer (<=0xFFFF).")

        # Split the channel choice into two options.
        channel_hex = f"{channel:08x}"

        channell = int(channel_hex[4:], 16)

        # Set the channel registers.
        self._channel(channell)

    def get_channel(self):
        """gets the current channel setting

        The channel defines how many spaces along the grid
        the laser's frequency is displaced from the first channel frequency.

        See 9.6.1 Channel (Channel 0x30) [RW]

        :returns: channel as an integer.

        """
        # This concatenates the data bytestrings
        response = self._channel()

        channel = int.from_bytes(response, "big")

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

        See 9.8.7 Fine Tune Frequency (FTF 0x62) [RW]

        **???** It seems like this can be done with the laser running.

        :param ftf: The fine tune frequency adjustment in GHz
        """

        ftf = round(ftf * 1e3)

        # We will leave this bare. This way the user can set and handle
        # their own timing and check to make sure the laser has reached the
        # desired fine tuning frequency.
        # It WILL throw a "pending" error if the laser is on when setting.
        self._ftf(ftf)

    def get_fine_tuning(self):
        """
        This function returns the setting for the
        off grid tuning for the laser's frequency.

        See 9.8.7 Fine Tune Frequency (FTF 0x62) [RW]

        :return ftf: The fine tune frequency adjustment in GHz
        """

        response = self._ftf()
        ftf = int.from_bytes(response, "big", signed=True)

        return ftf * 1e-3

    def get_ftf_range(self):
        """return the maximum and minimum off grid tuning for the laser's frequency.

        See 9.7.1 Fine Tune Frequency Range (FTF 0x4F) [R]

        :return ftfr: The fine tune frequency range [-ftfr, + ftfr] in GHz
        """
        response = self._ftfr()

        ftfr = int.from_bytes(response, "big")

        return ftfr * 1e-3

    def get_temps(self):
        """returns a list of technology specific temperatures
        units in deg C unless otherwise specified

        **Technologies**
        Technology 1: [Diode Temp, Case Temp]
        Technology 2: [Diode Temp, Case Temp]
        (why are they the same?)

        See 9.8.2 Module Temperatures (Temps 0x58) [R]

        :returns: list of temperatures in deg C
        """
        # get response this should be a long byte string
        response = self._temps()

        data = [
            int.from_bytes(response[i : i + 2], "big", signed=True) / 100
            for i in range(0, len(response), 2)
        ]

        return data

    def get_currents(self):
        """returns a list of technology specific currents in mA.

        **Technologies**
        Technology 1: [TEC, Diode]
        Technology 2: [TED, Diode 1, Diode 2, Diode 3, Diode 4, SOA]
        Technology 3: [TEC, Diode 1, tbd, tbd, tbd, ...]

        See 9.8.1 Module Currents (Currents 0x57) [R]

        :returns: list of currents in mA
        """
        # get response this should be a long byte string
        response = self._currents()

        data = [
            int.from_bytes(response[i : i + 2], "big", signed=True) / 10
            for i in range(0, len(response), 2)
        ]

        return data

    def get_last_response(self):
        """reads the last response sent from the laser

        This function gets the most recent response sent from the laser.
        The response is parsed for errors the way any normal response
        would be. The variable `self._response` is set to the last response again.

        See 9.4.12 Last Response (LstResp 0x13) [R]

        """
        return self._lstresp()

    def get_error_fatal(self, reset=False):
        """reads fatal error register statusf and checks each bit against the
        fatal error table to determine the fault

        See 9.5.1 StatusF, StatusW (0x20, 0x21) [RW]

        :param reset: resets/clears latching errors

        """
        response = self._statusf()
        statusf = int.from_bytes(response, "big")

        logger.debug("Current Status Fatal Error: %d", statusf)

        if reset:
            data_reset = 0x00FF
            self._statusf(data_reset)

        return FatalError(statusf)

    def get_error_warning(self, reset=False):
        """reads warning error register statusw and checks each bit against the
        warning error table to determine the fault

        If the laser is off then some of the latched warnings will be set on.

        See 9.5.1 StatusF, StatusW (0x20, 0x21) [RW]

        :param reset: resets/clears latching errors
        """
        response = self._statusw()
        statusw = int.from_bytes(response, "big")

        logger.debug("Current Status Warning Error: %d", statusw)

        if reset:
            data_reset = 0x00FF
            self._statusw(data_reset)

        return WarningError(statusw)

    def get_fatal_power_thresh(self):
        """reads maximum plus/minus power deviation in dB for which the fatal alarm is asserted

        See 9.5.2 Power Threshold (FPowTh, WPowTh 0x22, 0x23) [RW]
        """
        response = self._fpowth()
        pow_fatal = int.from_bytes(response, "big") / 100
        # correcting for proper order of magnitude
        return pow_fatal

    def get_warning_power_thresh(self):
        """reads maximum plus/minus power deviation in dB for which the warning alarm is asserted

        See 9.5.2 Power Threshold (FPowTh, WPowTh 0x22, 0x23) [RW]
        """
        response = self._wpowth()
        pow_warn = int.from_bytes(response, "big") / 100
        # correcting for proper order of magnitude
        return pow_warn

    def get_fatal_freq_thresh(self):
        """reads maximum plus/minus frequency deviation in GHz for which the fatal alarm is asserted

        See 9.5.3 Frequency Threshold (FFreqTh, WFreqTh 0x24, 0x25) [RW]
        """
        response = self._ffreqth()
        freq_fatal = int.from_bytes(response, "big") / 10
        return freq_fatal

    def get_warning_freq_thresh(self):
        """reads maximum plus/minus frequency deviation in GHz for which the warning alarm is asserted

        See 9.5.3 Frequency Threshold (FFreqTh, WFreqTh 0x24, 0x25) [RW]
        """
        response = self._wfreqth()
        freq_warn = int.from_bytes(response, "big") / 10
        return freq_warn

    def get_fatal_therm_thresh(self):
        """reads maximum plus/minus thermal deviation in degree celcius for which the fatal alarm is asserted

        See 9.5.4 Thermal Threshold (FThermTh, WThermTh 0x26, 0x27) [RW]
        """
        response = self._fthermth()
        therm_fatal = int.from_bytes(response, "big") / 100
        # correcting for proper order of magnitude
        return therm_fatal

    def get_warning_therm_thresh(self):
        """reads maximum plus/minus thermal deviation in degree celcius for which the warning alarm is asserted

        See 9.5.4 Thermal Threshold (FThermTh, WThermTh 0x26, 0x27) [RW]
        """
        response = self._wthermth()
        therm_thresh = int.from_bytes(response, "big") / 100
        # correcting for proper order of magnitude
        return therm_thresh

    def get_srq_trigger(self):
        """identifies corresponding bits in status registers StatusF, StatusW

        Utilizes SRQT register to identify why SRQ was asserted in StatusF and StatusW registers

        See 9.5.5 SRQ* Triggers (SRQT 0x28) [RW]
        """
        response = self._srqt()
        status = int.from_bytes(response, "big")

        logger.debug("SRQT Status: %d", status)

        return SQRTrigger(status)

    def get_fatal_trigger(self):
        """identifies which fatal condition was asserted in StatusF and StatusW registers

        See 9.5.6 FATAL Triggers (FatalT 0x29) [RW]
        """
        response = self._fatalt()
        status = int.from_bytes(response, "big")

        logger.debug("FatalT Status: %d", status)

        return FatalTrigger(status)

    def get_alm_trigger(self):
        """identifies why ALM was asserted in StatusF and StatusW registers

        See 9.5.7 ALM Triggers (ALMT 0x2A) [RW]
        """
        response = self._almt()
        status = int.from_bytes(response, "big")

        logger.debug("AlarmT Status: %d", status)

        return AlarmTrigger(status)
