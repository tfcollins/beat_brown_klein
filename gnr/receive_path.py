#!/usr/bin/env python

from gnuradio import gr, gru
from gnuradio import eng_notation
from gnuradio import digital
from gnuradio import fft
from gnuradio import window

import copy
import sys
import math


# /////////////////////////////////////////////////////////////////////////////
#                              receive path
# /////////////////////////////////////////////////////////////////////////////

class tune(gr.feval_dd):
    """
    This class allows C++ code to callback into python.
    """
    def __init__(self, tb):
        gr.feval_dd.__init__(self)
        self.tb = tb

    def eval(self, ignore):
        """
        This method is called from gr.bin_statistics_f when it wants
        to change the center frequency.  This method tunes the front
        end to the new center frequency, and returns the new frequency
        as its result.
        """

        try:
            # We use this try block so that if something goes wrong
            # from here down, at least we'll have a prayer of knowing
            # what went wrong.  Without this, you get a very
            # mysterious:
            #
            #   terminate called after throwing an instance of
            #   'Swig::DirectorMethodException' Aborted
            #
            # message on stderr.  Not exactly helpful ;)

            new_freq = self.tb.set_next_freq()
            return new_freq

        except Exception, e:
            print "tune: Exception: ", e


class parse_msg(object):
    def __init__(self, msg):
        self.center_freq = msg.arg1()
        self.vlen = int(msg.arg2())
        assert(msg.length() == self.vlen * gr.sizeof_float)

        # FIXME consider using NumPy array
        t = msg.to_string()
        self.raw_data = t
        self.data = struct.unpack('%df' % (self.vlen,), t)



class receive_path(gr.hier_block2):
    def __init__(self, demod_class, rx_callback, options, source_block):
	gr.hier_block2.__init__(self, "receive_path",
				gr.io_signature(1, 1, gr.sizeof_gr_complex),
				gr.io_signature(0, 0, 0))
        
        options = copy.copy(options)    # make a copy so we can destructively modify

        self._verbose     = options.verbose
        self._bitrate     = options.bitrate  # desired bit rate

        self._rx_callback = rx_callback  # this callback is fired when a packet arrives


        self._demod_class = demod_class  # the demodulator_class we're using

        self._chbw_factor = options.chbw_factor # channel filter bandwidth factor

        # Get demod_kwargs
        demod_kwargs = self._demod_class.extract_kwargs_from_options(options)

	#Give hooks of usrp to blocks downstream
	self.source_block = source_block

	#########################################
	# Build Blocks
	#########################################	

        # Build the demodulator
        self.demodulator = self._demod_class(**demod_kwargs)

        # Make sure the channel BW factor is between 1 and sps/2
        # or the filter won't work.
        if(self._chbw_factor < 1.0 or self._chbw_factor > self.samples_per_symbol()/2):
            sys.stderr.write("Channel bandwidth factor ({0}) must be within the range [1.0, {1}].\n".format(self._chbw_factor, self.samples_per_symbol()/2))
            sys.exit(1)
        
        # Design filter to get actual channel we want
        sw_decim = 1
        chan_coeffs = gr.firdes.low_pass (1.0,                  # gain
                                          sw_decim * self.samples_per_symbol(), # sampling rate
                                          self._chbw_factor,    # midpoint of trans. band
                                          0.5,                  # width of trans. band
                                          gr.firdes.WIN_HANN)   # filter type
        self.channel_filter = gr.fft_filter_ccc(sw_decim, chan_coeffs)
        
        # receiver
        self.packet_receiver = \
            digital.demod_pkts(self.demodulator,
                               access_code=None,
                               callback=self._rx_callback,
                               threshold=-1)

        # Carrier Sensing Blocks
        alpha = 0.001
        thresh = 30   # in dB, will have to adjust
        self.probe = gr.probe_avg_mag_sqrd_c(thresh,alpha)

        # Display some information about the setup
        if self._verbose:
            self._print_verbage()


	# More Carrier Sensing with FFT
	#self.gr_vector_sink = gr.vector_sink_c(1024)
	#self.gr_stream_to_vector = gr.stream_to_vector(gr.sizeof_gr_complex*1, 1024)
	#self.gr_head = gr.head(gr.sizeof_gr_complex*1024, 1024)
	#self.fft = fft.fft_vcc(1024, True, (window.blackmanharris(1024)), True, 1)

	# Parameters
        usrp_rate = options.bitrate
	self.fft_size = 1024
	self.min_freq = 2.4e9-0.75e6
        self.max_freq = 2.4e9+0.75e6
	self.tune_delay = 0.001
	self.dwell_delay = 0.01

	s2v = gr.stream_to_vector(gr.sizeof_gr_complex, self.fft_size)

        mywindow = window.blackmanharris(self.fft_size)
        fft = gr.fft_vcc(self.fft_size, True, mywindow)
        power = 0
        for tap in mywindow:
            power += tap*tap

        c2mag = gr.complex_to_mag_squared(self.fft_size)

        # FIXME the log10 primitive is dog slow
        log = gr.nlog10_ff(10, self.fft_size,
                           -20*math.log10(self.fft_size)-10*math.log10(power/self.fft_size))

        # Set the freq_step to 75% of the actual data throughput.
        # This allows us to discard the bins on both ends of the spectrum.
        #self.freq_step = 0.75 * usrp_rate
        #self.min_center_freq = self.min_freq + self.freq_step/2
        #nsteps = math.ceil((self.max_freq - self.min_freq) / self.freq_step)
        #self.max_center_freq = self.min_center_freq + (nsteps * self.freq_step)

	self.freq_step = 1.5e6
        self.min_center_freq = self.min_freq
        nsteps = 1
        self.max_center_freq = self.max_freq

        self.next_freq = self.min_center_freq

        tune_delay  = max(0, int(round(self.tune_delay * usrp_rate / self.fft_size)))  # in fft_frames
        dwell_delay = max(1, int(round(self.dwell_delay * usrp_rate / self.fft_size))) # in fft_frames

        self.msgq = gr.msg_queue(16)
        self._tune_callback = tune(self)        # hang on to this to keep it from being GC'd
        stats = gr.bin_statistics_f(self.fft_size, self.msgq,
                                    self._tune_callback, tune_delay,
                                    dwell_delay)


	######################################################
	# Connect Blocks Together
	######################################################
	#channel-filter-->Probe_Avg_Mag_Sqrd
	#	       -->Packet_Receiver (Demod Done Here!!)
	#

	# connect FFT sampler to system
	#self.connect(self, self.gr_stream_to_vector, self.fft, self.gr_vector_sink)

	# connect block input to channel filter
	self.connect(self, self.channel_filter)

        # connect the channel input filter to the carrier power detector
        self.connect(self.channel_filter, self.probe)

        # connect channel filter to the packet receiver
        self.connect(self.channel_filter, self.packet_receiver)

	# FIXME leave out the log10 until we speed it up
        #self.connect(self.u, s2v, fft, c2mag, log, stats)
        self.connect(self.channel_filter, s2v, fft, c2mag, stats)

	######################################################
	# Info and Action Methods
	######################################################

    #def ss_queue(self):
    #	return self.msgq

    def set_freq_R(self, target_freq):#Receiver
        """
        Set the center frequency of receiver we're interested in.
        """
        #print "Target: " + str(target_freq)
	r = self.source_block.set_freq(target_freq)
        if r:
            return True

        return False

    def bitrate(self):
        return self._bitrate

    def samples_per_symbol(self):
        return self.demodulator._samples_per_symbol

    def differential(self):
        return self.demodulator._differential

    def carrier_sensed(self):
        """
        Return True if we think carrier is present.
        """
        #return self.probe.level() > X
        return self.probe.unmuted()

    def spectrum_power(self):
        """
	##MAY HAVE TO ADJUST FOR MORE ACCURATE UNDERSTANDING
        Return Level in dB of current power in spectrum
        """
        #return self.probe.level() > X
        return self.probe.level()

    def carrier_threshold(self):
        """
        Return current setting in dB.
        """
        return self.probe.threshold()

    def set_carrier_threshold(self, threshold_in_db):
        """
        Set carrier threshold.

        @param threshold_in_db: set detection threshold
        @type threshold_in_db:  float (dB)
        """
        self.probe.set_threshold(threshold_in_db)
    
    def fft_sample(self):
        """
	Return FFT vector
        """
        data = self.gr_vector_sink.data()       
	self.gr_vector_sink.clear()
	return data 

    def add_options(normal, expert):
        """
        Adds receiver-specific options to the Options Parser
        """
        if not normal.has_option("--bitrate"):
            normal.add_option("-r", "--bitrate", type="eng_float", default=100e3,
                              help="specify bitrate [default=%default].")
        normal.add_option("-v", "--verbose", action="store_true", default=False)
        expert.add_option("-S", "--samples-per-symbol", type="float", default=2,
                          help="set samples/symbol [default=%default]")
        expert.add_option("", "--log", action="store_true", default=False,
                          help="Log all parts of flow graph to files (CAUTION: lots of data)")
        expert.add_option("", "--chbw-factor", type="float", default=1.0,
                          help="Channel bandwidth = chbw_factor x signal bandwidth [defaut=%default]")

    # Make a static method to call before instantiation
    add_options = staticmethod(add_options)


    def _print_verbage(self):
        """
        Prints information about the receive path
        """
        print "\nReceive Path:"
        print "modulation:      %s"    % (self._demod_class.__name__)
        print "bitrate:         %sb/s" % (eng_notation.num_to_str(self._bitrate))
        print "samples/symbol:  %.4f"    % (self.samples_per_symbol())
        print "Differential:    %s"    % (self.differential())



    def set_next_freq(self):
        target_freq = self.next_freq
        self.next_freq = self.next_freq + self.freq_step
        if self.next_freq > self.max_center_freq:
            self.next_freq = self.min_center_freq

        if not self.set_freq_R(target_freq):
            print "Failed to set frequency to", target_freq
            sys.exit(1)

        return target_freq



