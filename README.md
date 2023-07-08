# Scene Switch for AppDaemon

Control multiple switches from one scene switch. To switch between multiple scenes turn the main scene switch off and back on within 1 second.

## Arguments

- `scene_switch`: entity id of the main switch which will be used as a scene switch.
- `off_scene`: dictionary of entity id as a key and the state as a value when the Scene Switch is off (typically the value will be `off`)
- `on_scenes`: list of scenes; each scene has a `name` attribute and a `switches` attribute, which is a dictionary of entity id as a key and the state as a value for when this scene is on
- `state_snapshot_seconds`: number of seconds to remember the last scene when off; after that time turning back the scene switch on will activate the first scene.

At least one on scene is required. 

## Example

```yaml
lower_deck_light_remote:
  module: scene-switch
  class: SceneSwitch
  scene_switch: light.lower_deck_light_remote
  off_scene:
    light.lower_deck_light: "off"
    light.backyard_string: "off"
  on_scenes:
    - name: Deck
      switches:
        light.lower_deck_light: "on"
        light.backyard_string: "off"
    - name: Deck & Backyard String
      switches:
        light.lower_deck_light: "on"
        light.backyard_string: "on"
    - name: Backyard String
      switches:
        light.lower_deck_light: "off"
        light.backyard_string: "on"
  state_snapshot_seconds: 60
```