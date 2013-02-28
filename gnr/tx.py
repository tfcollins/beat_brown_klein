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

import numpy    

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
        self.rxpath = receive_path(demod_class, rx_callback, options, self.source)
        self.connect(self.txpath, self.sink)
        self.connect(self.source, self.rxpath)

    def send_pkt(self, payload='', eof=False):
        return self.txpath.send_pkt(payload, eof)

    def get_send_queue_size(self):
        return self.txpath.get_send_queue_size()
 
    def carrier_sensed(self):
        """
        Return True if the receive path thinks there's carrier
        """
        return self.rxpath.carrier_sensed()

    def spectrum_power(self):
        """
        Return Probe data from 
        """
        return self.rxpath.spectrum_power()

    def fft_sample(self):
        """
        Return Data from FFT Sink
        """
        return self.rxpath.fft_sample()

    def set_freq(self, target_freq):
        """
        Set the center frequency we're interested in.
        """

        self.sink.set_freq(target_freq)
        self.source.set_freq(target_freq)
        
    def set_freq_R(self, target_freq):#Receiver
        """
        Set the center frequency of receiver we're interested in.
        """
        self.source.set_freq(target_freq)

    def get_center_freq(self):#Transmitter
        """
        Get the center frequency we're interested in.
        """
	return self.sink.get_center_freq()
        
    def ss_msgq(self):#Spectrum Sensing Data
	return self.rxpath.msgq

# SS Message Parser

class parse_msg(object):
    def __init__(self, msg):
        self.center_freq = msg.arg1()
        self.vlen = int(msg.arg2())
        assert(msg.length() == self.vlen * gr.sizeof_float)

        # FIXME consider using NumPy array
        t = msg.to_string()
        self.raw_data = t
        self.data = struct.unpack('%df' % (self.vlen,), t)


#Sense spectrum
def sense_spectrum(tb):
	
	queue = tb.rxpath.msgq

	#Clear Queue for fresh data
	queue.flush()



	#Wait for message for channel 1
	# Get the next message sent from the C++ code (blocking call).
	# It contains the center frequency and the mag squared of the fft
	c1 = parse_msg(queue.delete_head())

	# Print center freq so we know that something is happening...
	#print "Channel 1: ", c1.center_freq
	#print c1.data

	c2 = parse_msg(queue.delete_head())

	# Print center freq so we know that something is happening...
	#print "Channel 2:", c2.center_freq
	#print c2.data

	return {'c1':c1, 'c2':c2}



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

	


	#####################################
	# MAIN MAC LOOP, where all the magic happens
	#####################################


    def main_loop(self, rx_freq):
        """
        Main loop for MAC.

        """
        min_delay = 1               # seconds
	main = rx_freq
	
	print '##############################'
	print 'Starting Control Mechanism'
	print '##############################'
        
	while 1:
            delay = min_delay
            #channel = self.tb.carrier_sensed()
            #power = self.tb.spectrum_power()
	    #print "Channel selected %d: " % channel
	    #print "Spectrum Power: %d dB" % power
	    
	    # Sense Spectrum
	    channel_info = sense_spectrum(self.tb)
	    print "Channel 1: ",channel_info['c1'].center_freq
	    print "Channel 2: ",channel_info['c2'].center_freq


	    # Channel Analysis
	    channel1=numpy.asarray(channel_info['c1'].data)
	    channel2=numpy.asarray(channel_info['c2'].data)

	    channel1ac=autocorr(channel1)
	    channel2ac=autocorr(channel2)
	    
	    channel1=channel1ac.mean()
	    channel2=channel2ac.mean()
 
	    print "Channel 1 Energy: ", channel1, " | Channel 2 Energy: ", channel2
		
	    # Set Channel Carrier Frequency
	    offset = 0.75e6
	    #if channel1>channel2:
	    if 1:
		print "USING CHANNEL 2"
		channel=main+offset # Middle of upper band
	    else:
		print "USING CHANNEL 1"
		channel=main-offset # Middle of lower band
	    print "Changing Carrier to: %d Hz" % channel
	    self.tb.set_freq(channel)
	    print "New Carrier Frequency: %d Hz" % self.tb.get_center_freq()


	    # Start Transmitting for certain period of time
	    print "Ima firin my lazer!!!"

	    # Start Timer
	    start = time.time()
	    packet = 'lawlz'
	    period = 5 # seconds
	    pkt_num = 0
	    while (time.time() - start) < period:
		pkt_num+=1
		self.tb.send_pkt(packet)	

	    print "Packet(s) Sent: %d" % pkt_num 
    	    #print "Queue size: ", self.tb.get_send_queue_size()
	    print "Waiting %d second(s) before sensing again" % delay
           
	    time.sleep(delay)

def autocorr(x):
    result = numpy.correlate(x, x, mode='full')
    return result[result.size/2:]

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

    mac.main_loop(options.tx_freq)    # don't expect this to return...

    tb.stop()     # but if it does, tell flow graph to stop.
    tb.wait()     # wait for it to finish
                

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
