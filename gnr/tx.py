#!/usr/bin/env python


from gnuradio import gr, digital
from gnuradio import eng_notation
from gnuradio.eng_option import eng_option
from optparse import OptionParser

# from current dir
from receive_path  import receive_path
from transmit_path import transmit_path
from uhd_interface import uhd_transmitter
from uhd_interface import uhd_receiver

import os, sys
import random, time, struct

    

# ////////////////////////////////////////////////////////////////////
#                     the flow graph
# ////////////////////////////////////////////////////////////////////

class my_top_block(gr.top_block):

    def __init__(self, mod_class, demod_class,
                 rx_callback, options):

        gr.top_block.__init__(self)

        # Get the modulation's bits_per_symbol
        args = mod_class.extract_kwargs_from_options(options)
        symbol_rate = options.bitrate / mod_class(**args).bits_per_symbol()

        self.source = uhd_receiver(options.args, symbol_rate,
                                   options.samples_per_symbol,
                                   options.rx_freq, options.rx_gain,
                                   options.spec, options.antenna,
                                   options.verbose)
        
        self.sink = uhd_transmitter(options.args, symbol_rate,
                                    options.samples_per_symbol,
                                    options.tx_freq, options.tx_gain,
                                    options.spec, options.antenna,
                                    options.verbose)
        
        options.samples_per_symbol = self.source._sps

        self.txpath = transmit_path(mod_class, options)
        self.rxpath = receive_path(demod_class, rx_callback, options)
        self.connect(self.txpath, self.sink)
        self.connect(self.source, self.rxpath)

    def send_pkt(self, payload='', eof=False):
        return self.txpath.send_pkt(payload, eof)

    def carrier_sensed(self):
        """
        Return True if the receive path thinks there's carrier
        """
        return self.rxpath.carrier_sensed()

    def spectrum_power(self):
        """
        Return True if the receive path thinks there's carrier
        """
        return self.rxpath.spectrum_power()

    def fft_sample(self):
        """
        Return True if the receive path thinks there's carrier
        """
        return self.rxpath.fft_sample()

    def set_freq(self, target_freq):
        """
        Set the center frequency we're interested in.
        """

        self.sink.set_freq(target_freq)
        self.source.set_freq(target_freq)
        

# ////////////////////////////////////////////////////////////////////
#                           Carrier Sense MAC
# ////////////////////////////////////////////////////////////////////

class cs_mac(object):
    """
    Prototype carrier sense MAC
    """

	#####################################
	# Accessories
	#####################################

    def __init__(self, verbose=False):
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
        #if self.verbose:
        #    print "Rx: ok = %r  len(payload) = %4d" % (ok, len(payload))
        #if ok:
        #    os.write(self.tun_fd, payload)

    def yamato_cannon(period):
	'Fire some data'
	
	#send dataz

	#####################################
	# MAIN MAC LOOP, where all the magic happens
	#####################################


    def main_loop(self):
        """
        Main loop for MAC.

        """
        min_delay = 1               # seconds

        while 1:
            delay = min_delay
            #channel = self.tb.carrier_sensed()
            power = self.tb.spectrum_power()
	    #print "Channel selected %d: " % channel
	    print "Spectrum Power: %d dB" % power
	    
	    # Start Transmitting for certain period of time
	    #print "Ima firing my lazer!!!"
	    #yamato_cannon(period)

	    # Channel Analysis
	    fft_data = self.tb.fft_sample()
	    channel1=sum(fft_data[0:511])
	    channel1=abs(channel1)
	    channel2=sum(fft_data[512:1024])
	    channel2=abs(channel2)
	    print "Channel 1 Energy: %.4f | Channel 2 Energy %.4f" % (channel1, channel2)


	    print "Waiting %d second(s) before sensing again" % delay
            time.sleep(delay)



# /////////////////////////////////////////////////////////////////////////////
#                                   main
# /////////////////////////////////////////////////////////////////////////////

def main():

    mods = digital.modulation_utils.type_1_mods()
    demods = digital.modulation_utils.type_1_demods()

    parser = OptionParser (option_class=eng_option, conflict_handler="resolve")
    expert_grp = parser.add_option_group("Expert")
    parser.add_option("-m", "--modulation", type="choice", choices=mods.keys(),
                      default='gmsk',
                      help="Select modulation from: %s [default=%%default]"
                            % (', '.join(mods.keys()),))

    parser.add_option("-s", "--size", type="eng_float", default=1500,
                      help="set packet size [default=%default]")
    parser.add_option("-v","--verbose", action="store_true", default=False)
    expert_grp.add_option("-c", "--carrier-threshold", type="eng_float", default=30,
                          help="set carrier detect threshold (dB) [default=%default]")
    #expert_grp.add_option("","--tun-device-filename", default="/dev/net/tun",
    #                      help="path to tun device file [default=%default]")

    transmit_path.add_options(parser, expert_grp)
    receive_path.add_options(parser, expert_grp)
    uhd_receiver.add_options(parser)
    uhd_transmitter.add_options(parser)

    for mod in mods.values():
        mod.add_options(expert_grp)

    for demod in demods.values():
        demod.add_options(expert_grp)

    (options, args) = parser.parse_args ()
    if len(args) != 0:
        parser.print_help(sys.stderr)
        sys.exit(1)


    # Attempt to enable realtime scheduling
    r = gr.enable_realtime_scheduling()
    if r == gr.RT_OK:
        realtime = True
    else:
        realtime = False
        print "Note: failed to enable realtime scheduling"

    # instantiate (create object) the MAC
    mac = cs_mac(verbose=True)

    # build the flow-graph (PHY)
    tb = my_top_block(mods[options.modulation],
                      demods[options.modulation],
                      mac.phy_rx_callback,
                      options)

    mac.set_top_block(tb)    # give the MAC a handle to control the PHY

    if tb.txpath.bitrate() != tb.rxpath.bitrate():
        print "WARNING: Transmit bitrate = %sb/sec, Receive bitrate = %sb/sec" % (
            eng_notation.num_to_str(tb.txpath.bitrate()),
            eng_notation.num_to_str(tb.rxpath.bitrate()))
             
    print "modulation:     %s"   % (options.modulation,)
    print "freq:           %s"      % (eng_notation.num_to_str(options.tx_freq))
    print "bitrate:        %sb/sec" % (eng_notation.num_to_str(tb.txpath.bitrate()),)
    print "samples/symbol: %3d" % (tb.txpath.samples_per_symbol(),)

    tb.rxpath.set_carrier_threshold(options.carrier_threshold)
    print "Carrier sense threshold:", options.carrier_threshold, "dB"

    tb.start()    # Start executing the flow graph (runs in separate threads)

    mac.main_loop()    # don't expect this to return...

    tb.stop()     # but if it does, tell flow graph to stop.
    tb.wait()     # wait for it to finish
                

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
