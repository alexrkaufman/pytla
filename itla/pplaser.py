from .itla import ITLA
from .itla_errors import *
from time import sleep
import yaml


class PPLaser(ITLA):
    """
    The pure photonics laser class implements specific features or handles particular
    quirks of the pure photonics laser. The pure photonics laser has additional
    registers for a couple of applications.

    * `set_frequency` and `set_fcf` had to be overridden
      * These are overwritten because fcf3 causes some issues
    * `get_frequency` is *not* overridden because these registers can still be read without issue
    """

    # TODO re-define init to run super() and but set baudrate for you
    def __init__(self, serial_port, baudrate=9600):
        super().__init__(serial_port, baudrate,
                         register_files={'registers_itla.yaml', 'registers_pp.yaml'})
        self._frequency_max = None
        self._frequency_min = None

    def connect(self):
        """Overriden connect function with query for max and min frequency
        """
        super().connect()
        self._frequency_max = self.get_frequency_max()
        self._frequency_min = self.get_frequency_min()

    def set_fcf(self, freq):
        '''
        This sets the first channel frequency.
        It does not reset the channel so this frequency will only be equal
        to the output frequency if channel=1.

        There is an issue in setting the first channel frequency for
        the pure photonics laser as compared to the ITLA 1.3 standard.

        If we set the FCF3 register it will clear the FCF2 register.

        Because the `set_frequency` function calls this function this will also
        correct the issue in setting the frequency generally.

        verifies that fcf is set within the appropriate laser frequency range
        and raises RVE error if not
        '''
        if freq < self._frequency_min or freq > self._frequency_max:
            raise RVEError("The desired frequency is outside "
                           "of the range for this laser.")

        freq = int(freq * 1e6)

        freq_str = str(freq)
        fcf1 = int(freq_str[0:3])
        fcf2 = int(freq_str[3:7])
        # the final two decimal places (0-99MHz) are ignored.

        try:
            self._fcf1(fcf1)
            self._fcf2(fcf2)

        except ExecutionError:

            try:
                self.nop()
            except RVEError as error:
                raise error from None
            except CIEError as error:
                raise error from None

    def set_channel(self, channel):
        """
        It is likely not possible to reach channels in the range where
        channelh would kick in anyway. However since the laser is built on the
        OIF-ITLA-1.2 standard we should just avoid calling it.
        """
        # check type and stuff
        if not isinstance(channel, int):
            raise TypeError("Channel must be an integer")
        if channel < 0:
            raise ValueError("Channel must be positive.")
        if channel > 0xFFFF:
            raise ValueError("Channel must be a 16 bit integer (<=0xFFFF).")

        # Split the channel choice into two options.
        channel_hex = f'{channel:08x}'

        channell = int(channel_hex[4:], 16)
        self._channel(channell)

    def set_grid(self, grid_freq):
        """
        Set the grid spacing in GHz. resolution in GHz/10.

        PPLaser built on 1.2 standard so we dont do grid2
        """
        grid_freq = int(grid_freq * 10)

        self._grid(grid_freq)

    def get_grid_min(self):
        """get the minimum grid spacing
        """
        try:
            self._lgrid()
            freq_lgrid = int(self._response[4:], 16)

        except ExecutionError as ee:
            self.nop()

        return freq_lgrid * 1e-1

    def get_mode(self):
        """get which low noise mode"""
        modes = {0: 'normal',
                 1: 'nodither',
                 2: 'whisper'}

        response = self._mode()
        response = int.from_bytes(response, 'big')

        return modes[response]

    def normalmode(self):
        """set mode to standard dither mode"""
        self._mode(0)

    def nodithermode(self):
        """Set mode to nodither mode

        It is unclear whether this just also activates whisper mode.
        The feature guide says "a value of 1 defaults to 2".
        """
        self._mode(1)

    def whispermode(self):
        """Enables whisper mode where all control loops
        are disabled resulting in a lower noise mode."""
        self._mode(2)

    def get_cleansweep_amplitude(self):
        """get the amplitude of the clean sweep.

        The clean sweep will ramp to (+0.5 to -0.5) * amplitude.
        (Basically it will be centered at the current frequency.)
        """
        response = self._csrange()
        cs_amplitude = int.from_bytes(response, 'big')

        return cs_amplitude

    def set_cleansweep_amplitude(self, range_GHz):
        """Sets the amplitude of the clean sweep.

        The clean sweep will ramp to (+0.5 to -0.5) * amplitude.
        (Basically it will be centered at the current frequency.)
        """
        self._csrange(range_GHz)

    def cleansweep_enable(self):
        """Enables clean sweep mode.
        The clean sweep will ramp to (+0.5 to -0.5) * amplitude.
        (Basically it will be centered at the current frequency.)
        """
        response = self.get_mode()
        if response == 'normal':
            raise Exception("Laser currently in normal mode.",
                            "please set to nodither or whisper mode")

        self._csstart(1)

    def cleansweep_disable(self):
        """Turn's off clean sweep mode."""

        self._csstart(0)

    def cleansweep_setup(self, freq_low, freq_high):
        """
        A wrapper function that takes the start and end frequencies
        you would like to sweep over. It computes and sets the clean sweep
        amplitude and the midpoint.

        The clean sweep operation will begin in the center of the high and low.

        """

        if freq_low < self._frequency_min or freq_high > self._frequency_max:
            raise ValueError('The range you would like to sweep over',
                             'is outside of the bounds for this laser')

        # sets the clean sweep amplitude rounded to the nearest MHz.
        cs_ampl = round(abs(freq_high - freq_low) * 1e3)
        if cs_ampl > 50:
            raise Exception("This is an error specific to SpectrumLab."
                            "Our laser has a 50GHz maximum cleansweep range."
                            "You should change the limit in source for your laser."
                            "If you know a way to query the laser for this value"
                            "then implementing that would be better.")

        self.set_cleansweep_amplitude(cs_ampl)

        cs_center = round((freq_low + freq_high) * 1e4 / 2) * 1e-4
        self.set_frequency(cs_center)

    def get_cleansweep_rate(self):
        """Gets the clean sweep rate. not sure about units."""
        response = self._csrate()
        cs_rate = int.from_bytes(response, 'big')
        return cs_rate

    def set_cleansweep_rate(self, rate_MHz):
        """sets the cleansweep rate in MHz/sec
        idk if there is a way to check if its within some bounds.
        There is conflicting info in the pure photonics docs."""
        raise Warning("Dont use this. Need to confirm the units for the sweep rate.")
        self._csrate(rate_MHz)

    def get_cleansweep_offset(self):
        raise Warning("This is not implemented yet.")

    def set_cleansweep_offset(self, offset):
        raise Warning("This is not implemented yet.")

    def cleanjump(self):
        """Tells the laser to perform the clean jump.
        The clean jump must be precalibrated.
        You should have the calibration points in your lab notebook
        or written down somewhere.
        If not you should perform the clean jump calibration."""
        mode = self.get_mode()
        if mode == 'normal':
            raise Exception("Laser in normal mode. You must be in nodither"
                            "or whisper mode to use cleanjump.")
        self._cjstart(1)

    def set_cleanjump(self, freq_jump):
        '''
        Set the size of the jump in THz to the fourth decimal place.
        XXX.XXXX
        '''
        freq_jump = str(freq_jump * 10000)
        self._cjthz(int(freq_jump[0:3]))
        self._cjghz(int(freq_jump[3:]))

    def cleanjump_calibration(self, fcf, grid, pwr, n_jumppoints,
                              confirmation=None):
        '''
        This is a grid based calibration

        **fcf**: the first channel frequency you would like to
        begin calibration at. (THz)

        **grid**: the grid spacing (GHz)

        **pwr**: The power calibration will be at. (dBm)

        **n_jumppoints**: The number of grid points to calibrate.

        **confirmation**: If you would like to go ahead and confirm yes
        and skip the user input you can set confirmation to 'y'
        '''

        # calibration begins by writing the number of channels to 0xD2

        calibration_points = [fcf + grid * n * 1e-3
                              for n in range(n_jumppoints)]

        print(f"You are calibrating {n_jumppoints} clean jump setpoints",
              f"at frequencies:\n{calibration_points}(THz).",
              f"With power = {pwr}(dBm).")
        print("Write these down in your lab notebook because",
              "you cannot query the device for these values later.")

        if confirmation is None:
            confirmation = input("Is the information above correct? (y/n): ")

        if confirmation.lower() == 'y':
            # set up the first channel frequency, grid spacing, and power
            self.set_frequency(fcf)
            self.set_grid(grid)
            self.set_power(pwr)
            self._cleanjump_calibration(n_jumppoints)

        elif confirmation.lower() == 'n':
            print(f"You answered {confirmation!r}.",
                  "Calibration will not be performed.")

        else:
            raise Exception("input not recognized")

    def _cleanjump_calibration(self, n_jumppoints):

        # does this return a response with bit 15 active?
        self._cjcalibration(n_jumppoints)

        is_calibrating = True

        while is_calibrating:

            response = self._cjcalibration()

            response_bits = [bit for bit in f'{response:08}'].reverse()
            is_calibrating = bool(response_bits[15])
            sleep(1)
