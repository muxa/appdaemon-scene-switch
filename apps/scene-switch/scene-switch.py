import hassapi as hass
import math
import datetime

class SceneSwitch(hass.Hass):
    def initialize(self):

        self.scene_switch = self.args["scene_switch"]
        self.off_scene = self.args["off_scene"]
        self.on_scenes = self.args["on_scenes"]
        self.state_snapshot_seconds = int(self.args["state_snapshot_seconds"])
        
        # these dictionaries are used to track toggling commands
        # (toggle does not happen immediately, so we need to track what toggled what to avoid cycling trigging)
        self.scene_switch_queue = {}
        self.linked_switch_queue = {}
        self.current_scene_index = 0 # 0 = off, 1 - first scene, etc

        # start listening to events from all switches
        self.listen_scene_switch_state()
        self.listen_linked_switches_state() 

        # these are used for timeout handlers
        self.apply_linked_switch_states_timeout_handle = None
        self.apply_scene_switch_state_timeout_handle = None

        self.delayed_off_handle = None
        self.scene_switch_last_off_time = None
        self.switch_states = None

        self.log(f'Initialised Scene Switch (scene_switch: {self.scene_switch}, off_scene: {self.off_scene}, on_scenes: {self.on_scenes}, state_snapshot_seconds: {self.state_snapshot_seconds})', level="DEBUG")

        self.sync_scene_switch_state()

    def listen_scene_switch_state(self):
        self.scene_switch_handle = self.listen_state(self.on_scene_switch_state, self.scene_switch)
    
    # def cancel_scene_switch_state(self):
    #     self.cancel_listen_state(self.scene_switch_handle)
    #     self.scene_switch_handle = None

    def listen_linked_switches_state(self):
        self.linked_switches_handles = []
        for switch in self.off_scene:
            self.linked_switches_handles.append(self.listen_state(self.on_linked_switch_state, switch))

        #self.linked_switches_handles = list(map(lambda s: self.listen_state(self.on_switch_state, s), self.off_scene.keys()))

        self.log('linked_switches_handles: %s', self.linked_switches_handles, level="DEBUG")
    
    # def cancel_linked_switches_state(self):
    #     for handle in self.linked_switches_handles:
    #         self.cancel_listen_state(handle)
    #     self.v = None

    def on_scene_switch_state(self, entity, attribute, old, new, kwargs):
        if old == 'unavailable':
            return

        if old == 'unavailable':
            self.sync_scene_switch_state()
            return

        if entity in self.scene_switch_queue:
            # this callback is caused by linked switch changing the scene switch
            self.scene_switch_queue.pop(entity, None)
            self.cancel_apply_scene_switch_state_timeout()
            self.cancel_delayed_off()
        else:
            # this callback is caused by the scene switch toggle

            self.log(f"SCENE {entity} {attribute} changed from {old} to {new}", level="DEBUG")

            if new == 'off':
                # remember states
                self.switch_states = { s : self.get_state(s) for s in self.off_scene.keys() }
                self.log(f'Saving previous switch state: {self.switch_states}', level="DEBUG")

                # start 
                self.scene_switch_last_off_time = datetime.datetime.now()
                self.delayed_off_handle = self.run_in(self.on_delayed_off, 1)

            elif new == 'on':
                if self.cancel_delayed_off():
                    # we are toggling between scenes
                    self.activate_scene(self.get_next_scene_index())
                else:
                    seconds_since_last_off = 0
                    if self.scene_switch_last_off_time:
                        seconds_since_last_off = (datetime.datetime.now() - self.scene_switch_last_off_time).total_seconds()
                        self.log(f'seconds_since_last_off: {seconds_since_last_off}', level="DEBUG")

                    # self.log(f'Last state: {self.switch_states}', level="DEBUG")

                    if self.switch_states != None and seconds_since_last_off < self.state_snapshot_seconds:
                        # restore saved states                    
                        self.current_scene_index = self.detect_scene_index(self.switch_states)
                        self.log(f'Restore last state (detected scene: {self.current_scene_index})', level="DEBUG")
                        self.apply_linked_switch_states(self.switch_states)
                    else:
                        # activate first scene
                        # we are switching on the lights (scene 1)
                        self.activate_scene(1)

    def on_delayed_off(self, kwargs):
        self.delayed_off_handle = None

        self.start_apply_linked_switch_states_timeout()

        self.activate_scene(0)
    
    def cancel_delayed_off(self):
        if self.delayed_off_handle != None:
            # we are toggling between scenes
            self.cancel_timer(self.delayed_off_handle)
            self.delayed_off_handle = None
            return True
        
        return False

    def start_apply_linked_switch_states_timeout(self):
        self.cancel_apply_linked_switch_states_timeout()

        self.apply_linked_switch_states_timeout_handle = self.run_in(self.on_apply_linked_switch_states_timeout, 3)

    def cancel_apply_linked_switch_states_timeout(self):
        if self.apply_linked_switch_states_timeout_handle != None:
            self.cancel_timer(self.apply_linked_switch_states_timeout_handle)
            self.apply_linked_switch_states_timeout_handle = None

    def on_apply_linked_switch_states_timeout(self, kwargs):
        self.apply_linked_switch_states_timeout_handle = None

        if len(self.linked_switch_queue) > 0:
            self.log('Timeout activating scene. Sync master switch', level='WARNING')
            self.sync_scene_switch_state()

    def on_linked_switch_state(self, entity, attribute, old, new, kwargs):
        if new == 'unavailable':
            return
        
        if old == 'unavailable':
            self.sync_scene_switch_state()
            return

        if entity in self.linked_switch_queue:
            # this callback is caused by the scene switch toggling the linked switches
            # TODO: detect if linked switch is manually toggled while scene is changing
            self.linked_switch_queue.pop(entity, None)

            if len(self.linked_switch_queue) == 0:
                self.cancel_apply_linked_switch_states_timeout()

                self.log("Scene fully applied", level="DEBUG")

        else:
            self.log(f"LINKED {entity} {attribute} changed from {old} to {new}", level="DEBUG")

            self.cancel_delayed_off()

            if new == 'on':
                self.apply_scene_switch_state('on', True)
            elif new == 'off' and self.is_off_scene():
                # all are off
                self.apply_scene_switch_state('off', True)


    def start_apply_scene_switch_state_timeout(self):
        self.cancel_apply_scene_switch_state_timeout()

        self.apply_scene_switch_state_timeout_handle = self.run_in(self.on_apply_scene_switch_state_timeout, 3)

    def cancel_apply_scene_switch_state_timeout(self):
        if self.apply_scene_switch_state_timeout_handle != None:
            self.cancel_timer(self.apply_scene_switch_state_timeout_handle)
            self.apply_scene_switch_state_timeout_handle = None

    def on_apply_scene_switch_state_timeout(self, kwargs):
        self.apply_scene_switch_state_timeout_handle = None
        self.log(f"Scene switch not toggled. Sync master switch", level="WARNING")
        self.sync_scene_switch_state()

    def apply_scene_switch_state(self, desired_state, start_timeout = False):
        if self.get_state(self.scene_switch) != desired_state:
            self.scene_switch_queue = { self.scene_switch: desired_state }
            #self.log(f"scene_switch_queue: {self.scene_switch_queue}")
            self.call_service(f"homeassistant/turn_{desired_state}", entity_id = self.scene_switch)

            if start_timeout:
                self.start_apply_scene_switch_state_timeout()

    def get_current_scene(self):
        return { s : self.get_state(s) for s in self.off_scene.keys() }


    def get_filtered_switches(self, state):
        #self.log(f'Current scene: {self.get_current_scene().items()}', level='DEBUG')
        filtered_switches = list(map(lambda x: x[0], filter(lambda x: x[1] == state, self.get_current_scene().items())))
        #self.log(f'Switches that are {state}: {filtered_switches}', level='DEBUG')

        return filtered_switches

    def is_off_scene(self):
        #return self.get_current_scene() == self.off_scene
        return len(self.get_filtered_switches('on')) == 0

    def sync_scene_switch_state(self):
        # update scene switch status to reflect linked switches state (e.g. after HA restarted)

        current_scene = self.get_current_scene()
        if 'unavailable' in current_scene.values():
            self.log(f'Unable to sync, as some entities are unavailable: {current_scene}', level='WARNING')
            return
        
        # self.log(f'Current scene: {self.get_current_scene()}', level='DEBUG')
        # self.log(f'Off scene: {self.off_scene}', level='DEBUG')
        # if len(self.get_filtered_switches('on')) == 0:
        #     self.log(f'No ON switches', level='DEBUG')
        # else:
        #     self.log(f'Some switches are ON', level='DEBUG')
        
        desired_scene_state = 'off' if self.is_off_scene() else 'on'
        self.log(f'Sync scene switch. Desired state: {desired_scene_state}', level='DEBUG')
        self.apply_scene_switch_state(desired_scene_state)

        self.current_scene_index = 0 if desired_scene_state == 'off' else 1

    def get_next_scene_index(self):
        if self.current_scene_index<0:
            return 1
        elif self.current_scene_index < len(self.on_scenes):
            return self.current_scene_index + 1
        else:
            return 1 # cycle to the first scene
    
    def detect_scene_index(self, desired_state):
        # scans state of linked switches and detect which scene that combination is matchi

        current_on_switches = set(map(lambda x: x[0], filter(lambda x: x[1] == 'on', desired_state.items())))
        #self.log(f'Current on switches: {current_on_switches}', level="DEBUG")

        if len(current_on_switches) == 0:
            return 0

        for i, scene in enumerate(self.on_scenes):
            if current_on_switches == set(scene['switches'].keys()):
                return i + 1

        return -1

    def activate_scene(self, scene_index):        

        if scene_index > 0:
            scene = self.on_scenes[scene_index - 1]
            desired_state = scene['switches']
            self.log(f"Activating scene {scene['name']} (switches: {desired_state})", level="DEBUG")

        # elif scene_index < 0:
        #     self.log(f"Restoring previous switches", level="DEBUG")
        else:
            self.log(f"Activating off scene", level="DEBUG")
            desired_state = self.off_scene
        
        self.apply_linked_switch_states(desired_state)            

        self.current_scene_index = scene_index
    
    def apply_linked_switch_states(self, desired_state):
        #self.log(f"Applying desired switch states: {desired_state}", level="DEBUG")
        self.linked_switch_queue = self.get_linked_switch_queue(desired_state)
        self.log(f"Queue: {self.linked_switch_queue}", level="DEBUG")

        switches_to_turn_on = list(map(lambda x: x[0] , filter(lambda x: x[1] == 'on', self.linked_switch_queue.items())))
        switches_to_turn_off = list(map(lambda x: x[0] , filter(lambda x: x[1] == 'off', self.linked_switch_queue.items())))

        if len(switches_to_turn_on) > 0:
            self.call_service("homeassistant/turn_on", entity_id = switches_to_turn_on)
        
        if len(switches_to_turn_off) > 0:
            self.call_service("homeassistant/turn_off", entity_id = switches_to_turn_off)
        
        if len(switches_to_turn_on) > 0 or len(switches_to_turn_off) > 0:
            self.start_apply_linked_switch_states_timeout()

    def get_linked_switch_queue(self, desired_state):
        return dict(map(lambda x: (x[0], x[1]), filter(lambda x: x[1] != x[2], map(lambda x: (x[0], x[1], self.get_state(x[0])), desired_state.items()))))
    