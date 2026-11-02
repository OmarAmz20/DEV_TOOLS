"""Window structures as well as colours; portable GTK 3 / GTK 4 CSS."""
from pathlib import Path

SKINS={
    'auto':('Follow recipe','Use the window structure designed for this recipe'),
    'modern':('Modern','Soft controls, quiet borders'),
    'pixel':('Pixel Arcade','Square pixels, hard shadows, chunky outlines'),
    'kingdom':('Mushroom Kingdom','Mario-inspired brick titlebars and coin-gold controls'),
    'handheld':('Pocket Console','Monochrome LCD, inset screens and block controls'),
    'classic':('Retro Desktop 95','Raised buttons, bevels and compact titlebars'),
    'neon':('Neon Grid','Thin luminous edges and angular controls'),
    'paper':('Paper & Ink','Ink outlines, offset paper shadows'),
    'glass':('Ocean Glass','Soft translucent surfaces and rounded controls'),
    'crt':('Terminal CRT','Dark green screens and sharp phosphor borders'),
}
RECIPE_SKINS={'pixel':'pixel','kingdom':'kingdom','handheld':'handheld','retro95':'classic',
              'cyber':'neon','paper':'paper','ocean':'glass','crt':'crt'}


def selected(config):
    value=config.get('skin','auto')
    return RECIPE_SKINS.get(config.get('preset'),'modern') if value=='auto' else value if value in SKINS else 'modern'


def pixel_style(config):return selected(config) in ('pixel','kingdom','handheld','crt')


def css(p,config):
    skin=selected(config)
    if skin=='modern':return ''
    border=p['accent'];ink=p['ink'];paper=p['paper'];sheet=p['sheet'];muted=p['muted']
    font='Silkscreen' if pixel_style(config) and config.get('pixel_font',True) else 'Sans'
    rules=f'/* Studio window structure: {skin} */\n'
    if pixel_style(config):
        rules+=f'''
window, .background, headerbar, .titlebar, button, entry, spinbutton, popover > contents,
menu, .menu, .card, .boxed-list, .navigation-sidebar, .view, textview, list, row,
.studio-hero, .studio-recipe, .studio-thumb, .studio-preview, .studio-toolbar,
.studio-nav row, .studio-method, .studio-photo {{ border-radius: 0; }}
headerbar, .titlebar {{ min-height: 34px; border-bottom: 3px solid {border}; background-image: none; }}
button:not(.flat):not(.circular) {{ background-image: none; border: 2px solid {border};
    box-shadow: 3px 3px 0 alpha({ink},.35); border-radius: 0; }}
button:not(.flat):active {{ box-shadow: inset 2px 2px 0 alpha({ink},.35); }}
entry, spinbutton, .view, textview {{ border: 2px solid alpha({border},.65); box-shadow: inset 2px 2px 0 alpha({ink},.12); }}
popover > contents, menu, .menu {{ border: 2px solid {border}; box-shadow: 4px 4px 0 alpha({ink},.35); }}
progressbar trough, progressbar progress, scale trough, scale highlight, switch, switch slider {{ border-radius: 0; }}
progressbar progress, scale highlight {{ background-image: none; border: 1px solid {ink}; }}
scrollbar slider {{ border-radius: 0; min-width: 8px; min-height: 8px; background-color: {muted}; }}
decoration {{ border: 2px solid {border}; border-radius: 0; box-shadow: 5px 5px 0 alpha({ink},.3); }}
.titlebar button.titlebutton {{ border: 2px solid {border}; border-radius: 0; min-width: 16px; min-height: 16px; }}
windowcontrols button, windowcontrols button > image, .titlebutton image {{ border-radius: 0; background-image: none; }}
'''
        if config.get('pixel_font',True):rules+=f'* {{ font-family: "{font}", monospace; }}\ntextview, terminal {{ font-family: monospace; }}\n'
    if skin=='kingdom':
        tile=(Path(__file__).resolve().parent.parent/'data/skins/brick.svg').as_uri()
        rules+=f'''
headerbar, .titlebar {{ background-color: #733C22; background-image: url("{tile}");
    background-repeat: repeat; color: #FFF5D6; border-bottom: 4px solid #E5AB35; }}
headerbar label, .titlebar label, headerbar image, .titlebar image {{ color: #FFF5D6; }}
headerbar button, .titlebar button {{ background-color: #63331C; color: #FFF5D6; border-color: #E5AB35; }}
button.suggested-action {{ background-color: {p['accent']}; color: {p['on_accent']}; border: 3px solid shade({p['accent']},.5); box-shadow: 3px 3px 0 shade({p['accent']},.5); }}
checkbutton check:checked, switch:checked {{ background-color: #367B35; color: #FFFFFF; border: 2px solid #173E21; }}
.navigation-sidebar row:selected, .sidebar row:selected {{ background-color: #367B35; color: white; }}
'''
    elif skin=='classic':
        rules+=f'''
window.csd, headerbar, .titlebar, button, entry, popover > contents, .card, .studio-hero, .studio-recipe {{ border-radius: 0; }}
headerbar, .titlebar {{ background-color: {border}; color: {p['on_accent']}; background-image: none; min-height: 30px; }}
headerbar label, .titlebar label {{ color: {p['on_accent']}; }}
button:not(.flat) {{ border: 2px solid; border-color: shade({sheet},1.35) shade({paper},.5) shade({paper},.5) shade({sheet},1.35);
    background-color: {sheet}; background-image: none; box-shadow: inset 1px 1px 0 shade({sheet},1.18); }}
button:active {{ border-color: shade({paper},.5) shade({sheet},1.35) shade({sheet},1.35) shade({paper},.5); }}
entry, textview, .view {{ border: 2px inset {muted}; border-radius: 0; }}
decoration {{ border: 3px ridge {muted}; border-radius: 0; }}
'''
    elif skin in ('neon','crt'):
        rules+=f'''
headerbar, .titlebar {{ border-bottom: 2px solid {border}; background-image: none; }}
button:not(.flat), entry, popover > contents {{ border: 1px solid {border}; border-radius: 3px; box-shadow: 0 0 4px alpha({border},.24); }}
window.csd {{ border-radius: 4px; }}
decoration {{ border: 1px solid {border}; box-shadow: 0 0 9px alpha({border},.28); }}
'''
    elif skin=='paper':
        rules+=f'''
window.csd, headerbar, .titlebar, button, entry, .card, .studio-recipe {{ border-radius: 3px; }}
headerbar, .titlebar {{ border-bottom: 2px solid {ink}; background-image: none; }}
button:not(.flat), entry, popover > contents {{ border: 2px solid {ink}; box-shadow: 3px 3px 0 alpha({ink},.2); }}
decoration {{ border: 2px solid {ink}; border-radius: 3px; box-shadow: 6px 6px 0 alpha({ink},.2); }}
'''
    elif skin=='glass':
        rules+=f'''
window.csd {{ border-radius: 20px; }}
headerbar, .titlebar {{ background-color: alpha({sheet},.93); background-image: none; border-bottom: 1px solid alpha({ink},.13); }}
button:not(.flat), entry, .card {{ border-radius: 14px; border: 1px solid alpha({ink},.16); }}
popover > contents {{ border-radius: 18px; border: 1px solid alpha({ink},.18); }}
decoration {{ border-radius: 20px; box-shadow: 0 8px 24px alpha(#000000,.3); }}
'''
    if skin=='handheld':rules+=f'headerbar, .titlebar {{ border: 3px ridge {muted}; }}\n.view, textview {{ border: 4px inset {muted}; }}\n'
    return rules
