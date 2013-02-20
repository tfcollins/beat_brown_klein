#!/usr/bin/env python
##################################################
# Gnuradio Python Flow Graph
# Title: Top Block
# Generated: Wed Feb 20 09:58:15 2013
##################################################

from gnuradio import digital
from gnuradio import eng_notation
from gnuradio import fft
from gnuradio import gr
from gnuradio import uhd
from gnuradio import window
from gnuradio.eng_option import eng_option
from gnuradio.gr import firdes
from optparse import OptionParser
import numpy

class top_block(gr.top_block):

	def __init__(self):
		gr.top_block.__init__(self, "Top Block")

		##################################################
		# Variables
		##################################################
		self.samp_rate = samp_rate = 1000000

	
		# Build System
		##################################################
		# Blocks
		##################################################
		self.uhd_usrp_source_0 = uhd.usrp_source(
			device_addr="",
			stream_args=uhd.stream_args(
				cpu_format="fc32",
				channels=range(1),
			),
		)
		self.uhd_usrp_source_0.set_samp_rate(samp_rate)
		self.uhd_usrp_source_0.set_center_freq(0, 0)
		self.uhd_usrp_source_0.set_gain(0, 0)
		self.uhd_usrp_sink_0 = uhd.usrp_sink(
			device_addr="",
			stream_args=uhd.stream_args(
				cpu_format="fc32",
				channels=range(1),
			),
		)
		self.uhd_usrp_sink_0.set_samp_rate(samp_rate)
		self.uhd_usrp_sink_0.set_center_freq(0, 0)
		self.uhd_usrp_sink_0.set_gain(0, 0)
		self.random_source_x_0 = gr.vector_source_b(map(int, numpy.random.randint(0, 2, 1000)), True)
		self.gr_vector_sink_x_0 = gr.vector_sink_c(1024)
		self.gr_stream_to_vector_0 = gr.stream_to_vector(gr.sizeof_gr_complex*1, 1024)
		self.gr_head_0 = gr.head(gr.sizeof_gr_complex*1024, 1024)
		self.fft_vxx_0 = fft.fft_vcc(1024, True, (window.blackmanharris(1024)), True, 1)
		self.digital_gmsk_mod_0 = digital.gmsk_mod(
			samples_per_symbol=2,
			bt=0.35,
			verbose=False,
			log=False,
		)

		##################################################
		# Connections
		##################################################
		self.connect((self.digital_gmsk_mod_0, 0), (self.uhd_usrp_sink_0, 0))
		self.connect((self.random_source_x_0, 0), (self.digital_gmsk_mod_0, 0))
		self.connect((self.uhd_usrp_source_0, 0), (self.gr_stream_to_vector_0, 0))
		self.connect((self.gr_stream_to_vector_0, 0), (self.fft_vxx_0, 0))
		self.connect((self.fft_vxx_0, 0), (self.gr_head_0, 0))
		self.connect((self.gr_head_0, 0), (self.gr_vector_sink_x_0, 0))


	def get_samp_rate(self):
		return self.samp_rate

	def set_samp_rate(self, samp_rate):
		self.samp_rate = samp_rate
		self.uhd_usrp_sink_0.set_samp_rate(self.samp_rate)
		self.uhd_usrp_source_0.set_samp_rate(self.samp_rate)


	def carrier_sensed(self):
	"""
	Return True if the receive path thinks there's carrier
	"""
		return self.rxpath.carrier_sensed()

	def set_freq(self, target_freq):
	"""
	Set the center frequency we're interested in.
	"""
		self.sink.set_freq(target_freq)
		self.source.set_freq(target_freq)
	

###########
# MAC Layer
###########
ass cs_mac(object):
    """
    Prototype carrier sense MAC
    """

    def __init__(self, tun_fd, verbose=False):
        self.tun_fd = tun_fd       # file descriptor for TUN/TAP interface
        self.verbose = verbose
        self.tb = None             # top block (access to PHY)

    def set_top_block(self, tb):
        self.tb = tb

    def phy_rx_callback(self, ok, payload):
        """
        Invoked by thread associated with PHY to pass received packet up.

        @param ok: bool indicating whether payload CRC was OK
        @param payload: contents of the packet (string)
        """
        if self.verbose:
            print "Rx: ok = %r  len(payload) = %4d" % (ok, len(payload))
        if ok:
            os.write(self.tun_fd, payload)

    def main_loop(self):
        """
        Main loop for MAC.

        """
        min_delay = 0.001               # seconds

        while 1:
		channel=self.tb.carrier_sensed():
		print "Channel Selected: %d: " % channel
		print "Waiting %d seconds before next sense" % min_delay	
                time.sleep(delay)



if __name__ == '__main__':
	parser = OptionParser(option_class=eng_option, usage="%prog: [options]")
	(options, args) = parser.parse_args()
	if gr.enable_realtime_scheduling() != gr.RT_OK:
		print "Error: failed to enable realtime scheduling."
	tb = top_block()
	tb.start()
	raw_input('Press Enter to quit: ')
	tb.stop()

