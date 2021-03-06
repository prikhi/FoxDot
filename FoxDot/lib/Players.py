"""
    Making music with FoxDot Players
    --------------------------------
    
    Players are what make FoxDot make music. They are similar in design to
    SuperCollider's `PDef` and `PBind` combo but with slicker syntax. FoxDot
    uses SuperCollider to *actually* make the sound and does so by triggering
    predefined `SynthDefs` - sort of like definitions of a digital instruments.
    To have a look at the list of `SynthDefs`, you can just `print` them to
    the console:

    ```python
    print SynthDefs
    ```

    Each one of these represents a `SynthDef` *object*. These objects are then
    given to Players to play - like giving an instrument to someone in your
    orchestra. To give someone the instrument, `pads`, you use a double arrow
    some code syntax like this:

    ```python
    p1 >> pads()
    ```

    `p1` is the name of a predefined player object. At startup, FoxDot reserves
    all one- and two-character variable names, such as `x`, `p1`, or `bd` for
    player objects but these can be repurposed if you like. If you want to use
    a variable name for a player object with more than two characters, you just
    instantiate a new `Player` object:

    ```python
    new_player = Player()

    new_player >> pads()
    ```

    Changing parameters
    -------------------

    By default, player objects play the first note of their default scale (more
    below) with a duration of 1 beat per note. To change the pitch just give the
    `SynthDef` a list of numbers.

    ```python
    p1 >> pads([0,7,6,4])
    ```

    Play multiple pitches together by putting them in round brackets:

    p1 >> pads([0,2,4,(0,2,4)])

    When you start FoxDot up, your clock is ticking at 120bpm and your player
    objects are all playing in the major scale. With 8 pitches in the major scale,
    the 0 refers to the first pitch and the 7 refers to the pitch one octave
    higher because Python, like most programming languages, uses zero-indexing.
    To change your scale you can specify a new scale as a keyword argument (see
    the documentation on `Scales` for more information on scales) or change the
    default scale for all player objects.

    ```python
    # Changing scale as a keyword argument
    p1 >> pads([0,7,6,4], scale=Scale.minor)

    # Changing the default scalew (the following are equivalent)
    Scale.default.set("minor")
    Scale.default.set(Scale.minor)
    Scale.default.set([0,2,3,5,7,8,10])

    # See a list of scales
    print Scale.names()

    # Change the tempo (this takes effect at the next bar)
    Clock.bpm = 144
    ```

    To change the rhythm of your player object, specify the durations using
    the `dur` keyword. Other keywords can be specified, such as `oct` for the
    octave and `sus` for the sustain, which is the same as the duration by
    default.

    ```python
    p1 >> pads([0,7,6,4], dur=[1,1/2,1/4,1/4], oct=6, sus=1)

    # See a list of possible keyword arguments
    print Player.Attributes()
    ```

    Using the `play` SynthDef
    -------------------------

    There is a special case SynthDef object called `play` which allows you
    to play short audio files rather than specify pitches. In this case
    you use a string of characters as the first argument where each character
    refers to a different folder of audio files. You can see more information
    by evaluating `print Samples`. The following line of code creates
    a basic drum beat:

    ```python
    d1 >> play("x-o-")
    ```

    To play multiple patterns simultaneously, you can create a new `play` object. This
    is useful if you want to have different attributes for each player.

    ```python
    bd >> play("x( x)  ", dur=1)
    hh >> play("---[--]", dur=[1/2,1/2,1/4], rate=4)
    sn >> play("  o ", rate=(.9,1), pan=(-1,1))
    ```    

    Grouping characters in round brackets laces the pattern so that on each
    play through of the sequence of samples, the next character in the group's
    sample is played. The sequence `(xo)---` would be played back as if it
    were entered `x---o---`. Using square brackets will force the enclosed samples
    to played in the same time span as a single character e.g. `--[--]` will play
    two hi-hat hits at a half beat then two at a quarter beat. You can play a
    random sample from a selection by using curly braces in your Play String
    like so:

    ```
    d1 >> play("x-o{-[--]o[-o]}")
    ```

    FoxDot Player Object Keywords
    -----------------------------

    dur - Durations (defaults to 1 and 1/2 for the Sample Player)

    sus - Sustain (defaults to `dur`)

    amp - Amplitude (defaults to 1)

    rate - Variable keyword used for misc. changes to a signal. E.g. Playback rate of the Sample Player (defaults to 1)

    delay - A duration of time to wait before sending the information to SuperCollider (defaults to 0)

    sample - Special keyword for Sample Players; selects another audio file from the bank of samples for a sample character.
    

"""

from __future__ import division

from os.path import dirname
from random import shuffle, choice
from copy import copy, deepcopy
from time import sleep

from Settings import SamplePlayer, LoopPlayer
from Code import WarningMsg, debug_stdout
from SCLang.SynthDef import SynthDefProxy, SynthDef
from Effects import FxList

from Repeat import *
from Patterns import *
from Midi import *

from Root import Root
from Scale import Scale

from Bang import Bang

import Buffers
import TimeVar

class Player(Repeatable):

    # Set private values

    debug = 0

    __vars = []
    __init = False

    # These are used by FoxDot
    keywords   = ('degree', 'oct', 'freq', 'dur', 'delay', 'buf',
                  'blur', 'amplify', 'scale', 'bpm', 'sample')

    internal_keywords = tuple(value for value in keywords if value != "degree")

    # Base attributes
    base_attributes = ('sus', 'fmod', 'vib', 'pan', 'rate', 'amp', 'midinote', 'channel')

    fx_attributes = FxList.all_kwargs()
    fx_keys       = FxList.kwargs()

    metro   = None
    server  = None
    samples = None

    # Tkinter Window
    widget = None

    default_scale = Scale.default()
    default_root  = Root.default()


    def __init__( self ):

        # Inherit

        Repeatable.__init__(self)
    
        # General setup
        
        self.synthdef = None
        self.id = None
        self.quantise = False
        self.stopping = False
        self.stop_point = 0
        self.following = None
        self.queue_block = None
        self.playstring = ""
        self.buf_delay = []
        self.timestamp = 0

        # Visual feedback information

        self.envelope    = None
        self.line_number = None
        self.whitespace  = None
        self.bang_kwargs = {}

        # Modifiers
        
        self.reversing = False
        self.degrading = False
        
        # Keeps track of which note to play etc

        self.event_index = 0
        self.event_n = 0
        self.notes_played = 0
        self.event = {}

        # Used for checking clock updates

        self.current_dur = None
        self.old_pattern_dur = None
        self.old_dur = None
        
        self.isplaying = False
        self.isAlive = True

        # These dicts contain the attribute and modifier values that are sent to SuperCollider     

        self.attr  = {}
        self.modifier = []
        self.mod_data = 0

        # Keyword arguments that are used internally

        self.scale = None
        self.offset  = 0
        self.following = None
        
        # List the internal variables we don't want to send to SuperCollider

        self.__vars = self.__dict__.keys()
        self.__init = True

        self.reset()

    # Class methods

    @classmethod
    def Attributes(cls):
        return cls.keywords + cls.base_attributes + cls.fx_attributes

    # Player Object Manipulation
    
    def __rshift__(self, other):
        """ Handles the allocation of SynthDef objects using >> syntax """
        
        if isinstance(other, SynthDefProxy):
            self.update(other.name, other.degree, **other.kwargs)
            self + other.mod
            for method, arguments in other.methods.items():
                args, kwargs = arguments
                getattr(self, method).__call__(*args, **kwargs)                
            return self
        
        raise TypeError("{} is an innapropriate argument type for PlayerObject".format(other))
        return self

    def __setattr__(self, name, value):
        if self.__init:

            # Force the data into a Pattern if the attribute is used with SuperCollider
            
            if name not in self.__vars:

                value = asStream(value)

                # Update the attribute dict
                
                self.attr[name] = value

                # keep track of what values we change with +-

                if (self.synthdef == SamplePlayer and name == "sample") or (self.synthdef != SamplePlayer and name == "degree"):

                    self.modifier = value

                # Update any playerkey

                if name in self.__dict__:

                    if isinstance(self.__dict__[name], PlayerKey):
    
                        self.__dict__[name].update_pattern()

                return
            
        self.__dict__[name] = value
        return

    def __getitem__(self, name):
        if self.__init:
            if name not in self.__vars:
                return self.attr[name]
            pass
        return self.__dict__[name]

    def __eq__(self, other):
        return self is other

    def __ne__(self, other):
        return not self is other

    # --- Startup methods

    def reset(self):
        """ Sets all Player attributes to 0 unless their default is specified by an effect """

        # Add all keywords to the dict, then set non-zero defaults

        for key in Player.Attributes():

            if key != "scale":

                self.attr[key] = asStream(0)

                if key not in self.__dict__:

                    self.__dict__[key] = PlayerKey(0, parent=self, attr=key)

                elif not isinstance(self.__dict__[key], PlayerKey):

                    self.__dict__[key] = PlayerKey(0, parent=self, attr=key) 

                else:

                    self.__dict__[key].update(0)

        # Set any non zero defaults for effects, e.g. verb=0.25

        for key in Player.fx_attributes:

            value = FxList.defaults[key]

            setattr(self, key, value)

        # Set any non-zero values for FoxDot

        # Sustain & Legato
        self.sus     = 1
        self.blur    = 1

        # Amplitude
        self.amp     = 1
        self.amplify = 1

        # Duration of notes
        self.dur     = 0.5 if self.synthdef == SamplePlayer else 1

        # Degree of scale / Characters of samples
        self.degree  = " " if self.synthdef is SamplePlayer else 0

        # Octave of the note
        self.oct     = 5
        
        # Tempo
        self.bpm     = None 
        
        return self

    # --- Update methods

    def __call__(self, **kwargs):

        # If stopping, kill the event

        if self.stopping and self.metro.now() >= self.stop_point:
            self.kill()
            return

        # If the duration has changed, work out where the internal markers should be

        force_count = kwargs.get("count", False)
        dur_updated = self.dur_updated()

        if dur_updated or force_count is True:

            try:

                self.event_n, self.event_index = self.count(self.event_index if not force_count else None)

                if self.debug:

                    if dur_updated:

                        print self.event_index, self.metro.now()

            except TypeError as e:

                print e

                print("TypeError: Innappropriate argument type for 'dur'")

            # self.old_dur = self.attr['dur']

        # Get the current state

        dur = 0

        while True:

            self.get_event()
            
            # Set a 'None' to 0

            if self.event['dur'] is None:

                dur = 0

            # If there are more than one dur (happens sometimes because of threading), only use first

            try:

                if len(self.event['dur']) > 0:

                    self.event['dur'] = self.event['dur'][0]                    

            except TypeError:

                pass

            finally:

                dur = float(self.event['dur'])

            # Skip events with durations of 0

            if dur == 0:

                self.event_n += 1

            else:

                break

        # Play the note  

        if self.metro.solo == self and kwargs.get('verbose', True) and type(self.event['dur']) != rest: 

            self.send()

        # If using custom bpm

        if self.event['bpm'] is not None:

            try:

                tempo_shift = float(self.metro.bpm) / float(self.event['bpm'])

            except (AttributeError, TypeError, ZeroDivisionError):

                tempo_shift = 1

            dur *= tempo_shift

        # Schedule the next event

        self.event_index = self.event_index + dur

        self.metro.schedule(self, self.event_index, kwargs={})

        # Change internal marker

        self.event_n += 1 
        self.notes_played += 1

        return

    def count(self, time=None, event_after=False):
        """ Counts the number of events that will have taken place between 0 and `time`. If
            `time` is not specified the function uses self.metro.now(). Setting `event_after`
            to `True` will find the next event *after* `time`"""

        n = 0
        acc = 0
        dur = 0
        now = (time if time is not None else self.metro.now())
        bpm = float(self.metro.bpm if self.bpm == None else self.bpm) # TODO: use this to better caclulate event_index -- why?

        durations = self.rhythm() if self.current_dur is None else self.current_dur
        total_dur = float(sum(durations))

        if total_dur == 0:

            WarningMsg("Player object has a total duration of 0. Set to 1")

            durations = [1]
            total_dur =  1 
            self.dur  =  1
    
        acc = now - (now % total_dur)

        try:

            n = int(len(durations) * (acc / total_dur))

        except TypeError as e:

            WarningMsg(e)

            self.stop()

            return 0, 0

        if acc != now:

            while True:

                dur = float(modi(durations, n))

                if acc + dur == now:

                    acc += dur

                    n += 1

                    break

                elif acc + dur > now:

                    if event_after:

                        acc += dur
                        n += 1

                    break

                else:
                    
                    acc += dur
                    n += 1

        # Store duration times

        # self.old_dur = self.attr['dur']

        # Returns value for self.event_n and self.event_index

        return n, acc

    def rhythm(self):
        rhythm = []
        for value in self.attr['dur']:
            if isinstance(value, TimeVar.TimeVar):
                rhythm.append(value.now())
            else:
                rhythm.append(value)
        self.current_dur = asStream(rhythm)
        return self.current_dur

    def update(self, synthdef, degree, **kwargs):

        # SynthDef name
        
        self.synthdef = synthdef

        if self.isplaying is False:

            self.reset() # <-- need to reset effects

        # If there is a designated solo player when updating, add this at next bar
        
        if self.metro.solo.active() and self.metro.solo != self:

            self.metro.schedule(lambda *args, **kwargs: self.metro.solo.add(self), self.metro.next_bar())

        # Update the attribute values

        special_cases = ["scale", "root", "dur"]

        # Set the degree

        if synthdef == SamplePlayer:

            if type(degree) == str:

                self.playstring = degree

            else:

                self.playstring = None

            if degree is not None:

                setattr(self, "degree", degree if len(degree) > 0 else " ")

        elif degree is not None:

            self.playstring = str(degree)

            setattr(self, "degree", degree)

        # Set special case attributes

        self.scale = kwargs.get("scale", self.__class__.default_scale )
        self.root  = kwargs.get("root",  self.__class__.default_root )

        # If only duration is specified, set sustain to that value also

        if "dur" in kwargs:

            self.dur = kwargs['dur']

            if "sus" not in kwargs and synthdef != SamplePlayer:

                self.sus = self.attr['dur']

        # Set any other attributes

        for name, value in kwargs.items():

            if name not in special_cases:

                setattr(self, name, value)

        # Calculate new position if not already playing

        if self.isplaying is False:

            # Add to clock
            
            self.isplaying = True
            self.stopping = False
            
            next_bar = self.metro.next_bar()
            self.event_n = 0

            self.event_n, self.event_index = self.count(next_bar, event_after=True)
            
            self.metro.schedule(self, self.event_index)

        return self

    def dur_updated(self):
        dur = self.rhythm()
        if dur != self.old_dur:
            self.old_dur = dur
            return True
        return False

    def step_duration(self):
        return 0.5 if self.synthdef is SamplePlayer else 1

    def pattern_rhythm_updated(self):
        r = self.rhythm()
        if self.old_pattern_dur != r:
            self.old_pattern_dur = r
            return True
        return False

    def char(self, other=None):
        if other is not None:
            try:
                if type(other) == str and len(other) == 1: #char
                    return self.samples.bufnum(self.now('buf')) == other
                raise TypeError("Argument should be a one character string")
            except:
                return False
        else:
            try:
                return self.samples.bufnum(self.now('buf'))
            except:
                return None

    def calculate_freq(self):
        """ Uses the scale, octave, and degree to calculate the frequency values to send to SuperCollider """

        # If the scale is frequency only, just return the degree

        if self.scale == Scale.freq:
            
            try:

                return list(self.event['degree'])

            except:

                return [self.event['degree']]

        now = {attr: self.event[attr] for attr in ('degree', 'oct')}

        size = LCM( get_expanded_len(now['oct']), get_expanded_len(now['degree']) )

        f = []

        for i in range(size):

            try:
                
                midinum = midi( self.scale, group_modi(now['oct'], i), group_modi(now['degree'], i) , self.now('root') )

            except Exception as e:

                print e

                WarningMsg("Invalid degree / octave arguments for frequency calculation, reset to default")

                print now['degree'], modi(now['degree'], i)

                raise

            f.append( miditofreq(midinum) )
            
        return f

    def f(self, *data):

        """ adds value to frequency modifier """

        self.fmod = tuple(data)

        p = []
        for val in self.attr['fmod']:

            try:
                pan = tuple((item / ((len(val)-1) / 2.0))-1 for item in range(len(val)))
            except:
                pan = 0
            p.append(pan)

        self.pan = p

        return self

    # Methods affecting other players - every n times, do a random thing?

    def stutter(self, n=2, **kwargs):
        """ Plays the current note n-1 times. You can specify keywords. """

        self.get_event()

        n = int(n)

        if self.metro.solo == self and n > 0:

            other_kwarg = { "timestamp": self.metro.osc_message_time(),
                            "delay": 0,
                            }

            dur = float(kwargs.get("dur", self.dur)) / n

            delay = 0

            size = self.largest_attribute()

            for stutter in range(1, n):

                other_kwarg["delay"] = other_kwarg["delay"] + dur

                # Use a custom attr dict and specify the first delay to play "immediately"

                sub = {kw: modi(val, stutter-1) for kw, val in kwargs.items() + other_kwarg.items()}

                self.send(**sub)
                
        return self
    
    # --- Misc. Standard Object methods

    def __int__(self):
        return int(self.now('degree'))

    def __float__(self):
        return float(self.now('degree'))

    def __add__(self, data):
        """ Change the degree modifier stream """
        self.mod_data = data
        if self.synthdef == SamplePlayer:
            self.attr['sample'] = self.modifier + self.mod_data
        else:
            self.attr['degree'] = self.modifier + self.mod_data
        return self

    def __sub__(self, data):
        """ Change the degree modifier stream """
        self.mod_data = 0 - data
        if self.synthdef == SamplePlayer:
            self.attr['sample'] = self.modifier + self.mod_data
        else:
            self.attr['degree'] = self.modifier + self.mod_data
        return self

    def __mul__(self, data):
        return self

    def __div__(self, data):
        return self

    # --- Data methods

    def __iter__(self):
        for _, value in self.event.items():
            yield value

    def number_of_layers(self):
        """ Returns the deepest nested item in the event """
        num = 1
        for attr, value in self.event.items():
            if isinstance(value, PGroup):
                l = pattern_depth(value)
            else:
                l = 1                
            if l >  num:
                num = l
        return num                

    def largest_attribute(self):
        """ Returns the length of the largest nested tuple in the current event dict """

        size = 1
        values = []

        for attr, value in self.event.items():
            l = get_expanded_len(value)
            if l > size:
                size = l
        return size

    def number_attr(self, attr):
        """ Returns true if the attribute should be a number """
        return not (self.synthdef == SamplePlayer and attr in ("degree", "freq"))

    # --- Methods for preparing and sending OSC messages to SuperCollider

    def unpack(self, item):
        """ Converts a pgroup to floating point values and updates and time var or playerkey relations """

        if isinstance(item, TimeVar.TimeVar):

                item = item.now()

        if isinstance(item, PlayerKey):
            
            if item.parent in self.queue_block.objects() and item.parent is not self:

                self.queue_block.call(item.parent, self)

            item = item.now()

        if isinstance(item, PGroup):

            item =  item.convert_data(self.unpack)

        return item

    def now(self, attr="degree", x=0):
        """ Calculates the values for each attr to send to the server at the current clock time """

        index = self.event_n + x

        attr_value = modi(self.attr[attr], index)

        if attr_value is not None:

            attr_value = self.unpack(attr_value)

        return attr_value

    def get_event(self):
        """ Returns a dictionary of attr -> now values """

        attributes = copy(self.attr)

        prime_funcs = {}
        
        for key in attributes:

            value = self.event[key] = self.now(key)

            if isinstance(value, (PlayerKey, TimeVar.TimeVar)): ##

                value = value.now()

            # Look for PGroupPrimes

            if isinstance(value, PGroup):

                if value.has_behaviour():

                    name = value.__class__.__name__
                    
                    getaction = True

                    if name in prime_funcs:

                        if len(value) <= len(prime_funcs[name][1]):

                            getaction = False

                    if getaction:

                        prime_funcs[name] = [key, value, value.get_behaviour()]

            #  Make sure the object's dict uses PlayerKey instances

            if key not in self.__dict__:

                self.__dict__[key] = PlayerKey(value, parent=self, attr=key)

            elif not isinstance(self.__dict__[key], PlayerKey):

                self.__dict__[key] = PlayerKey(value, parent=self, attr=key) 

            else:

                self.__dict__[key].update(value)

        # Add largest PGroupPrime function

        for name, func in prime_funcs.items():

            prime_call = func[-1]

            if prime_call is not None:

                self.event = prime_call(self.event, func[0])
        
        return self


    def osc_message(self, index=0, **kwargs):
        """ Creates an OSC packet to play a SynthDef in SuperCollider,
            use kwargs to force values in the packet, e.g. pan=1 will force ['pan', 1] """

        message = {}
        fx_dict = {}

        # Calculate frequency / buffer number

        if self.synthdef == SamplePlayer:

            degree = group_modi(kwargs.get("degree", self.event['degree']), index)
            sample = group_modi(kwargs.get("sample", self.event["sample"]), index)

            buf  = int(self.samples[str(degree)].bufnum(sample))
            
            message = {'buf': buf}

        elif self.synthdef == LoopPlayer:

            pos = group_modi(kwargs.get("degree", self.event["degree"]), index)
            # sus = group_modi(kwargs.get("dur", self.event["dur"]), index)

            buf = group_modi(kwargs.get("buf", self.event["buf"]), index)

            # Work out the position from the rhythm

##            if pos > 0: # not quite right? does it in number of beats somehow
##
##                durations = self.rhythm() if self.current_dur is None else self.current_dur
##
##                total_dur, num_dur = float(sum(durations)), len(durations)
##
##                loops = pos // total_dur
##
##                rmndr = pos % num_dur
##
##                steps = int(rmndr)
##
##                rmndr = rmndr - steps
##
##                accum = (loops * total_dur) + sum(durations[n] for n in range(steps)) + rmndr
##
##                pos = self.metro.beat_dur(acc)

            pos *= self.metro.beat_dur(1)

            message = {'pos': pos, 'buf': buf}

        else:

            degree = group_modi(kwargs.get("degree", self.event["degree"]), index)
            octave = group_modi(kwargs.get("oct", self.event["oct"]), index)
            root   = group_modi(kwargs.get("root", self.event["root"]), index)

            midinote = midi( kwargs.get("scale", self.scale), octave, degree, root )

            freq   = miditofreq(midinote)
            
            message = {'freq':  freq, 'midinote': midinote}

        attributes = self.attr.copy()

        # Go through the attr dictionary and add kwargs

        for key in attributes:

            try:

                # Don't use fx keywords or foxdot keywords except "degree"

                if (key not in self.keywords) and (key not in self.fx_attributes or key in self.base_attributes):

                    group_value = kwargs.get(key, self.event[key])

                    val = float(group_modi(group_value, index))

                    ## DEBUG

                    if isinstance(val, (Pattern, PGroup)):

                        print "In osc_message:", key, group_value, self.event[key], val

                    # Special case modulation

                    if key == "sus":

                        val = val * float(self.metro.beat_dur()) * float(group_modi(kwargs.get('blur', self.event['blur']), index))

                    elif key == "amp":

                        val = val * float(group_modi(kwargs.get('amplify', self.event['amplify']), index))

                    # Only send non-zero values

                    if val != 0 or key in ("sus", "amp"):

                        message[key] = val

            except KeyError as e:

                WarningMsg("KeyError in function 'osc_message'", key, e)

        # See if any fx_attributes 

        for key in self.fx_keys:

            if key in attributes: 

                # Only use effects where the "title" effect value is not 0

                val = group_modi(kwargs.get(key, self.event[key]), index)

                if val != 0:

                    fx_dict[key] = []

                    # Look for any other attributes require e.g. room and verb

                    for n, sub_key in enumerate(FxList[key].args):

                        if sub_key in self.event:

                            # If the sub_key is another attribute like sus, get it from the message

                            if sub_key in message:

                                val = message[sub_key]

                            # Get the value from the event

                            else:

                                try:

                                    val = group_modi(kwargs.get(sub_key, self.event[sub_key]), index)

                                except TypeError as e:

                                    val = 0

                                except KeyError as e:

                                    del fx_dict[key]

                                    break

                            fx_dict[key] += [sub_key, val]

        return message, fx_dict


    def send(self, **kwargs):
        """ Sends the current event data to SuperCollder.
            Use kwargs to overide values in the """

        timestamp = kwargs.get("timestamp", self.queue_block.time)

        size  = self.largest_attribute() * pattern_depth(self.event.values())
        
        banged = False

        sent_messages = []
        delayed_messages = []

        freq = []
        bufnum = []

        last_msg = None

        for i in range(size):

            # Get the basic osc_msg

            osc_msg, effects = self.osc_message(i, **kwargs)

            if "freq" in osc_msg:

                freq_value = osc_msg["freq"]

                if freq_value not in freq:

                    freq.append(freq_value)

            # Look at delays and schedule events later if need be

            delay = float(group_modi(kwargs.get('delay', self.event.get('delay', 0)), i))

            if 'buf' in osc_msg:
                    
                buf = group_modi(kwargs.get('buf', osc_msg['buf']), i)

            else:

                buf = 0

            if buf not in bufnum:

                bufnum.append( buf )

            amp = group_modi(kwargs.get('amp', osc_msg['amp']), i)

            # Any messages with zero amps or 0 buf are not sent <- maybe change that for "now" classes

            if (self.synthdef != SamplePlayer and amp > 0) or (self.synthdef == SamplePlayer and buf > 0 and amp > 0):

                synthdef = self.get_synth_name(buf)

                key = (osc_msg, effects, delay)

                if key not in sent_messages:

                    # Keep note of what messages we are sending

                    sent_messages.append(key)

                    # Compile the message with time tag

                    delay = self.metro.beat_dur(delay)

                    compiled_msg = self.server.get_bundle(synthdef, osc_msg, effects, timestamp = timestamp + delay)

                    # Add the message to the appropriate queue block

                    self.queue_block.osc_messages.append(compiled_msg)

                    # "bang" the line

                    if not banged and self.bang_kwargs:

                        self.bang()

                        banged = True

        self.freq = freq
        self.buf = bufnum
        
        return

    def get_synth_name(self, buf=0):
        if self.synthdef == SamplePlayer:
            numChannels = self.samples.getBuffer(buf).channels
            if numChannels == 1:
                synthdef = "play1"
            else:
                synthdef = "play2"
        else:
            synthdef = str(self.synthdef)
        return synthdef

    #: Methods for stop/starting players

    def kill(self):
        """ Removes this object from the Clock and resets itself"""
        self.isplaying = False
        self.repeat_events = {}
        self.reset()
        return
        
    def stop(self, N=0):
        
        """ Removes the player from the Tempo clock and changes its internal
            playing state to False in N bars time
            - When N is 0 it stops immediately"""

        self.stopping = True        
        self.stop_point = self.metro.now()

        if N > 0:

            self.stop_point += self.metro.next_bar() + ((N-1) * self.metro.bar_length())

        else:

            self.kill()

        return self

    def pause(self):

        self.isplaying = False

        return self

    def play(self):

        self.isplaying = True
        self.stopping = False
        self.isAlive = True

        self.__call__()

        return self

    def accompany(self, other, values=[0,2,4]):
        """ Similar to "follow" but when the value has changed """

        if isinstance(lead, self.__class__):

            self.accompanying = lead.degree

        else:

            self.accompanying = None
        
        return self

    def find_accompanying(self, value):
        pass

    def follow(self, lead=False):
        """ Takes a Player object and then follows the notes """

        if isinstance(lead, self.__class__):

            self.degree = lead.degree + self.mod_data

            # self.following = lead

        # else:

            # self.following = None

        return self

    def solo(self, arg=True):

        if arg:
            
            self.metro.solo.set(self)

        else:

            self.metro.solo.reset()

        return self

    def num_key_references(self):
        """ Returns the number of 'references' for the
            attr which references the most other players """
        num = 0
        for attr in self.attr.values():
            if isinstance(attr, PlayerKey):
                if attr.num_ref > num:
                    num = attr.num_ref
        return num

    def lshift(self, n=1):
        self.event_n -= (n+1)
        return self

    def rshift(self, n=1):
        self.event_n += n
        return self

    def reverse(self):
        """ Sets flag to reverse streams """
        for attr in self.attr:
            try:
                self.attr[attr] = self.attr[attr].pivot(self.event_n)
            except AttributeError:
                pass
        return self

    def shuffle(self):
        """ Shuffles the degree of a player. """
        # If using a play string for the degree
        if self.synthdef == SamplePlayer and self.playstring is not None:
            # Shuffle the contents of playgroups among the whole string
            new_play_string = PlayString(self.playstring).shuffle()
            new_degree = Pattern(new_play_string).shuffle()
        else:            
            new_degree = self.attr['degree'].shuffle()
        self._replace_degree(new_degree)
        return self

    def mirror(self):
        """ The degree pattern is reversed """
        self._replace_degree(self.attr['degree'].mirror())
        return self

    def rotate(self, n=1):
        """ Rotates the values in the degree by 'n' """
        self._replace_degree(self.attr['degree'].rotate(n))
        return self

    def _replace_degree(self, new_degree):
        # Update the GUI if possible
        if self.widget:
            if self.synthdef == SamplePlayer:
                if self.playstring is not None:
                    # Replace old_string with new string (only works with plain string patterns)
                    new_string = new_degree.string()
                    self.widget.addTask(target=self.widget.replace, args=(self.line_number, self.playstring, new_string))
                    self.playstring = new_string
            else:
                # Replaces the degree pattern in the widget (experimental)
                # self.widget.addTask(target=self.widget.replace_re, args=(self.line_number,), kwargs={'new':str(new_degree)})
                self.playstring = str(new_degree)
        setattr(self, 'degree', new_degree)
        return

    def multiply(self, n=2):
        self.attr['degree'] = self.attr['degree'] * n
        return self

    def degrade(self, amount=0.5):
        """ Sets the amp modifier to a random array of 0s and 1s
            amount=0.5 weights the array to equal numbers """
        if not self.degrading:
            self.amp = Pwrand([0,1],[1-amount, amount])
            self.degrading = True
        else:
            ones = int(self.amp.count(1) * amount)
            zero = self.amp.count(0)
            self.amp = Pshuf(Pstutter([1,0],[ones,zero]))
        return self

    def changeSynth(self, list_of_synthdefs):
        new_synth = choice(list_of_synthdefs)
        if isinstance(new_synth, SynthDef):
            new_synth = str(new_synth.name)
        self.synthdef = new_synth
        # TODO, change the >> name
        return self

    """

        Modifier Methods
        ----------------

        Other modifiers for affecting the playback of Players

    """

    def offbeat(self, dur=0.5):
        """ Off sets the next event occurence """

        self.attr['delay'] += (dur-self.offset)

        self.offset = dur

        return self

    def strum(self, dur=0.025):
        """ Adds a delay to a Synth Envelope """
        x = self.largest_attribute()
        if x > 1:
            self.delay = asStream([tuple(a * dur for a in range(x))])
        else:
            self.delay = asStream(dur)
        return self

    def __repr__(self):
        return "a '%s' Player Object" % self.synthdef

    def info(self):
        s = "Player Instance using '%s' \n\n" % self.synthdef
        s += "ATTRIBUTES\n"
        s += "----------\n\n"
        for attr, val in self.attr.items():
            s += "\t{}\t:{}\n".format(attr, val)
        return s

    def bang(self, **kwargs):
        """
        Triggered when sendNote is called. Responsible for any
        action to be triggered by a note being played. Default action
        is underline the player
        """
        if kwargs:

            self.bang_kwargs = kwargs

        elif self.bang_kwargs:

            bang = Bang(self, self.bang_kwargs)

        return self

####

class PlayerKey(object):
    def __init__(self, value=None, reference=None, parent=None, attr=None):

        # Reference to the Player object that is using this
        self.parent = parent

        self.value   = asStream(value)
        self.key     = attr
        self.pattern = asStream(self.parent.attr[self.key])

        self.index = 0
        
        if reference is None:

            self.other   = 0
            self.num_ref = 0

        else:

            self.other   = reference
            self.parent  = reference.parent
            self.num_ref = reference.num_ref + 1
            
    @staticmethod
    def calculate(x, y):
        return x
    
    def update(self, value):
        self.value = asStream(value)

    def update_pattern(self):
        self.pattern[:] = asStream(self.parent.attr[self.key])               
        return

    def child(self, other):
        return PlayerKey(other, self, self.parent, self.key)
    
    def __add__(self, other):
        """ If operating with a pattern, return a pattern of values """
        if isinstance(other, (list, tuple)):
            other=asStream(other)
        if isinstance(other, metaPattern):
            return other.__radd__(self)
        new = self.child(other)
        new.calculate = Add
        return new

    def __radd__(self, other):
        """ If operating with a pattern, return a pattern of values """
        if isinstance(other, (list, tuple)):
            other=asStream(other)
        if isinstance(other, metaPattern):
            return other.__add__(self)
        new = self.child(other)
        new.calculate = Add
        return new
    
    def __sub__(self, other):
        """ If operating with a pattern, return a pattern of values """
        if isinstance(other, (list, tuple)):
            other=asStream(other)
        if isinstance(other, metaPattern):
            return other.__rsub__(self)
        new = self.child(other)
        new.calculate = rSub
        return new
    
    def __rsub__(self, other):
        """ If operating with a pattern, return a pattern of values """
        if isinstance(other, (list, tuple)):
            other=asStream(other)
        if isinstance(other, metaPattern):
            return other.__sub__(self)
        new = self.child(other)
        new.calculate = Sub
        return new
    
    def __mul__(self, other):
        """ If operating with a pattern, return a pattern of values """
        if isinstance(other, (list, tuple)):
            other=asStream(other)
        if isinstance(other, metaPattern):
            return other.__rmul__(self)
        new = self.child(other)
        new.calculate = Mul
        return new

    def __rmul__(self, other):
        """ If operating with a pattern, return a pattern of values """
        if isinstance(other, (list, tuple)):
            other=asStream(other)
        if isinstance(other, metaPattern):
            return other.__mul__(self)
        new = self.child(other)
        new.calculate = Mul
        return new
    
    def __div__(self, other):
        if isinstance(other, metaPattern):
            return other.__rdiv__(self)
        new = self.child(other)
        new.calculate = rDiv
        return new

    def __rdiv__(self, other):
        """ If operating with a pattern, return a pattern of values """
        if isinstance(other, (list, tuple)):
            other=asStream(other)
        if isinstance(other, metaPattern):
            return other.__div__(self)
        new = self.child(other)
        new.calculate = Div
        return new
    
    def __mod__(self, other):
        """ If operating with a pattern, return a pattern of values """
        if isinstance(other, (list, tuple)):
            other=asStream(other)
        if isinstance(other, metaPattern):
            return other.__rmod__(self)
        new = self.child(other)
        new.calculate = rMod
        return new
    
    def __rmod__(self, other):
        """ If operating with a pattern, return a pattern of values """
        if isinstance(other, (list, tuple)):
            other=asStream(other)
        if isinstance(other, metaPattern):
            return other.__mod__(self)
        new = self.child(other)
        new.calculate = Mod
        return new
    
    def __pow__(self, other):
        """ If operating with a pattern, return a pattern of values """
        if isinstance(other, (list, tuple)):
            other=asStream(other)
        if isinstance(other, metaPattern):
            return other.__rpow__(self)
        new = self.child(other)
        new.calculate = rPow
        return new
    
    def __rpow__(self, other):
        """ If operating with a pattern, return a pattern of values """
        if isinstance(other, (list, tuple)):
            other=asStream(other)
        if isinstance(other, metaPattern):
            return other.__pow__(self)
        new = self.child(other)
        new.calculate = Pow
        return new
    
    def __xor__(self, other):
        """ If operating with a pattern, return a pattern of values """
        if isinstance(other, (list, tuple)):
            other=asStream(other)
        if isinstance(other, metaPattern):
            return other.__rxor__(self)
        new = self.child(other)
        new.calculate = rPow
        return new
    
    def __rxor__(self, other):
        """ If operating with a pattern, return a pattern of values """
        if isinstance(other, (list, tuple)):
            other=asStream(other)
        if isinstance(other, metaPattern):
            return other.__xor__(self)
        new = self.child(other)
        new.calculate = Pow
        return new

    def __truediv__(self, other):
        """ If operating with a pattern, return a pattern of values """
        if isinstance(other, (list, tuple)):
            other=asStream(other)
        if isinstance(other, metaPattern):
            return other.__rtruediv__(self)
        new = self.child(other)
        new.calculate = rDiv
        return new
    
    def __rtruediv__(self, other):
        """ If operating with a pattern, return a pattern of values """
        if isinstance(other, (list, tuple)):
            other=asStream(other)
        if isinstance(other, metaPattern):
            return other.__truediv__(self)
        new = self.child(other)
        new.calculate = Div
        return new

    # Comparisons
    def __eq__(self, other):
        """ If operating with a pattern, return a pattern of values """
        if isinstance(other, (list, tuple)):
            other=asStream(other)
        if isinstance(other, metaPattern):
            return other.__ne__(self)
        new = self.child(other)
        new.calculate = lambda a, b: int(a == b)
        return new
    
    def __ne__(self, other):
        """ If operating with a pattern, return a pattern of values """
        if isinstance(other, (list, tuple)):
            other=asStream(other)
        if isinstance(other, metaPattern):
            return other.__eq__(self)
        new = self.child(other)
        new.calculate = lambda a, b: int(a != b)
        return new
    
    def __gt__(self, other):
        """ If operating with a pattern, return a pattern of values """
        if isinstance(other, (list, tuple)):
            other=asStream(other)
        if isinstance(other, metaPattern):
            return other.__lt__(self)
        new = self.child(other)
        new.calculate = lambda a, b: int(a < b)
        return new
    
    def __lt__(self, other):
        """ If operating with a pattern, return a pattern of values """
        if isinstance(other, (list, tuple)):
            other=asStream(other)
        if isinstance(other, metaPattern):
            return other.__gt__(self)
        new = self.child(other)
        new.calculate = lambda a, b: int(a > b)
        return new
    
    def __ge__(self, other):
        """ If operating with a pattern, return a pattern of values """
        if isinstance(other, (list, tuple)):
            other=asStream(other)
        if isinstance(other, metaPattern):
            return other.__le__(self)
        new = self.child(other)
        new.calculate = lambda a, b: int(a <= b)
        return new
    
    def __le__(self, other):
        """ If operating with a pattern, return a pattern of values """
        if isinstance(other, (list, tuple)):
            other=asStream(other)
        if isinstance(other, metaPattern):
            return other.__ge__(self)
        new = self.child(other)
        new.calculate = lambda a, b: int(a >= b)
        return new

    def __nonzero__(self):
        return int(self.now())

    # Values
    def __int__(self):
        return int(self.now())
    def __float__(self):
        return float(self.now())
    def __str__(self):
        return str(self.now())
    def __repr__(self):
        return repr(self.now())
    def __len__(self):
        return len(self.now())

    # Container
    def __getitem__(self, key):
        return self.now()[key]
    
    def __iter__(self):
        for item in self.now():
            yield item
    
    def now(self, step=1):
        if isinstance(self.other, self.__class__):
            other = self.other.now(step=0)
        else:
            other = self.other
        value = self.calculate(self.value[self.index], other)
        self.index += step
        return value

###### GROUP OBJECT

class Group:

    metro = None

    def __init__(self, *args):

        self.players = args

    def __len__(self):
        return len(self.players)

    def __str__(self):
        return str(self.players)

    def solo(self, arg=True):

        if self.metro is None:

            self.__class__.metro = Player.metro

        if arg:
            
            self.metro.solo.set(self.players[0])

            for player in self.players[1:]:

                self.metro.solo.add(player)

        else:

            self.metro.solo.reset()

        return self
        

    def iterate(self, dur=4):
        if dur == 0 or dur is None:
            self.amplify=1
        else:
            delay, on = 0, float(dur) / len(self.players)
            for player in self.players:
                player.amplify=TimeVar.TimeVar([0,1,0],[delay, on, dur-delay])
                delay += on
        return           

    def __setattr__(self, name, value):
        try:
            for p in self.players:
                try:
                    setattr(p, name, value)
                except:
                    WarningMsg("'%s' object has no attribute '%s'" % (str(p), name))
        except:
            self.__dict__[name] = value 
        return self        

    def __getattr__(self, name):
        """ Returns a Pattern object containing the desired attribute for each player in the group  """
        if name == "players":
            return self.players
        attributes = GroupAttr()
        for player in self.players:
            if hasattr(player, name):
                attributes.append(getattr(player, name))
        return attributes

class GroupAttr(list):
    def __call__(self, *args, **kwargs):
        for p in self:
            if callable(p):
                p.__call__(*args, **kwargs)

class rest(object):
    ''' Represents a rest when used with a Player's `dur` keyword
    '''
    def __init__(self, dur=1):
        self.dur = dur
    def __repr__(self):
        return "<rest: {}>".format(self.dur)
    def __add__(self, other):
        return rest(self.dur + other)
    def __radd__(self, other):
        return rest(other + self.dur)
    def __sub__(self, other):
        return rest(self.dur - other)
    def __rsub__(self, other):
        return rest(other - self.dur)
    def __mul__(self, other):
        return rest(self.dur * other)
    def __rmul__(self, other):
        return rest(other * self.dur)
    def __div__(self, other):
        return rest(self.dur / other)
    def __rdiv__(self, other):
        return rest(other / self.dur)
    def __truediv__(self, other):
        return rest(float(self.dur) / other)
    def __rtruediv__(self, other):
        return rest(other / float(self.dur))
    def __mod__(self, other):
        return rest(self.dur % other)
    def __rmod__(self, other):
        return rest(other % self.dur)
    def __int__(self):
        return int(self.dur)
    def __float__(self):
        return float(self.dur)
