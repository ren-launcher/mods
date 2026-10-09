# Copyright (c) 2026 RenLauncher contributors. MIT.

init python in rmods_variables:
    import store
    import types
    from store import renpy

    def owner(scope):
        return {"game": store, "persistent": store.persistent}[scope]

    def scalar(value):
        return type(value) in (bool, int, float, str)

    def browsable(value):
        return isinstance(value, (dict, list)) or (
            not isinstance(value, (types.ModuleType, type))
            and not callable(value)
            and hasattr(value, "__dict__")
        )

    def read(container, step):
        kind, key = step
        return vars(container)[key] if kind == "field" else container[key]

    def value(scope, path):
        current = owner(scope)
        for step in path:
            current = read(current, step)
        return current

    def rows(scope, path, query):
        current = value(scope, path)
        if isinstance(current, list):
            entries = [(('item', i), str(i), v) for i, v in enumerate(current)]
        elif isinstance(current, dict):
            entries = [(('item', k), repr(k), v) for k, v in current.items() if scalar(k)]
            entries.sort(key=lambda entry: entry[1])
        else:
            entries = [(('field', k), k, v) for k, v in vars(current).items() if not k.startswith("_")]
            entries.sort(key=lambda entry: entry[1])
        query = query.lower()
        return [
            entry for entry in entries
            if (scalar(entry[2]) or browsable(entry[2])) and query in entry[1].lower()
        ]

    def title(path):
        return "Variables" if not path else " → ".join(str(key) for kind, key in path)

    def preview(value):
        if scalar(value):
            return str(value)
        if isinstance(value, (dict, list)):
            return type(value).__name__ + " (" + str(len(value)) + ") >"
        return type(value).__name__ + " >"

    def apply(scope, path, text):
        current = value(scope, path)
        try:
            if type(current) is bool:
                converted = {"True": True, "False": False}[text]
            else:
                converted = type(current)(text)
        except ValueError:
            renpy.notify("Enter a valid " + type(current).__name__ + ".")
            return

        container = value(scope, path[:-1])
        kind, key = path[-1]
        if kind == "field":
            setattr(container, key, converted)
        else:
            container[key] = converted
        if scope == "persistent":
            renpy.save_persistent()
        else:
            # Preserve edits made during this interaction when saving immediately.
            renpy.retain_after_load()
        renpy.hide_screen("rmods_variable_value")
        renpy.restart_interaction()

init python:
    config.always_shown_screens.append("rmods_variables_button")

screen rmods_variables_button():
    zorder 90
    if not main_menu:
        button:
            style "rmods_icon_button"
            xalign 1.0
            yalign 0.08
            xoffset -12
            action Show("rmods_variables_panel")
            add "variable_editor/adjust.svg":
                xysize (int(config.screen_height * 0.035), int(config.screen_height * 0.035))
                align (0.5, 0.5)

screen rmods_dialog(title, screen_name, scrollable=False, confirm=None):
    style_prefix "rmods"
    key "game_menu" action Hide(screen_name)
    add Solid("#0009")
    frame:
        style "rmods_panel"
        align (0.5, 0.5)
        xsize int(config.screen_width * (0.68 if scrollable else 0.48))
        if scrollable:
            ysize int(config.screen_height * 0.78)
        vbox:
            spacing 12
            side "c r":
                xfill True
                spacing 12
                text title:
                    style "rmods_heading"
                    substitute False
                textbutton "×":
                    yalign 0.0
                    action Hide(screen_name)
            if scrollable:
                viewport:
                    mousewheel True
                    draggable True
                    scrollbars "vertical"
                    yfill True
                    vbox:
                        spacing 12
                        transclude
            else:
                vbox:
                    spacing 12
                    transclude
            if confirm is not None:
                textbutton "Apply":
                    xalign 1.0
                    action confirm

screen rmods_variables_panel():
    style_prefix "rmods"
    modal True
    zorder 100
    default scope = "game"
    default query = ""
    default path = ()
    use rmods_dialog(rmods_variables.title(path), "rmods_variables_panel", scrollable=True):
        hbox:
            spacing 12
            textbutton "Game":
                action [SetScreenVariable("scope", "game"), SetScreenVariable("query", ""), SetScreenVariable("path", ())]
                selected scope == "game"
            textbutton "Persistent":
                action [SetScreenVariable("scope", "persistent"), SetScreenVariable("query", ""), SetScreenVariable("path", ())]
                selected scope == "persistent"
        if path:
            textbutton "Back":
                action [SetScreenVariable("path", path[:-1]), SetScreenVariable("query", "")]
        if scope == "persistent":
            text "Changes are saved immediately." style "rmods_caption"
        frame:
            style "rmods_field"
            hbox:
                spacing 12
                add "variable_editor/search.svg":
                    xysize (int(config.screen_height * 0.028), int(config.screen_height * 0.028))
                    yalign 0.5
                input:
                    style "rmods_input"
                    value ScreenVariableInputValue("query", default=not renpy.get_screen("rmods_variable_value"))
                    xfill True
        vbox:
            spacing 0
            for step, name, current in rmods_variables.rows(scope, path, query):
                button:
                    style "rmods_row"
                    xfill True
                    if rmods_variables.scalar(current):
                        action [DisableAllInputValues(), Show("rmods_variable_value", scope=scope, path=path + (step,))]
                    else:
                        action [SetScreenVariable("path", path + (step,)), SetScreenVariable("query", "")]
                    hbox:
                        spacing 16
                        text name:
                            style "rmods_text"
                            substitute False
                            xsize int(config.screen_width * 0.32)
                        text "[rmods_variables.preview(current)!sq]":
                            style "rmods_caption"
                            layout "nobreak"
            if not rmods_variables.rows(scope, path, query):
                text "No matching fields." style "rmods_caption"

screen rmods_variable_value(scope, path):
    style_prefix "rmods"
    modal True
    zorder 110
    default draft = str(rmods_variables.value(scope, path))
    $ is_boolean = type(rmods_variables.value(scope, path)) is bool
    use rmods_dialog(rmods_variables.title(path), "rmods_variable_value", confirm=Function(rmods_variables.apply, scope, path, draft)):
        if is_boolean:
            hbox:
                spacing 12
                for choice in ("True", "False"):
                    textbutton choice:
                        action SetScreenVariable("draft", choice)
                        selected draft == choice
        else:
            frame:
                style "rmods_field"
                input:
                    style "rmods_input"
                    value ScreenVariableInputValue("draft")
                    xfill True

style rmods_text is default:
    font "DejaVuSans.ttf"
    size int(config.screen_height * 0.028)
    color "#edf0f8"
    outlines []

style rmods_heading is rmods_text:
    size int(config.screen_height * 0.035)

style rmods_caption is rmods_text:
    color "#b9c2d8"
    size int(config.screen_height * 0.025)

style rmods_input is rmods_text:
    color "#ffffff"

style rmods_panel is frame:
    background Solid("#171d2b")
    padding (20, 16)

style rmods_button is button:
    background None
    hover_background Solid("#ffffff12")
    selected_background Solid("#ffffff18")
    padding (12, 8)

style rmods_button_text is rmods_text

style rmods_row is button:
    background None
    hover_background Solid("#ffffff0c")
    padding (8, 8)

style rmods_icon_button is button:
    background Solid("#171d2b99")
    hover_background Solid("#171d2bdd")
    xysize (int(config.screen_height * 0.065), int(config.screen_height * 0.065))
    padding (0, 0)

style rmods_field is frame:
    background Solid("#ffffff0a")
    padding (12, 8)
    xfill True
