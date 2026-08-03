# tmux config

Prefix: `Ctrl-Space` (instead of default `Ctrl-b`)

## Sessions

| Shortcut | Action |
|----------|--------|
| `tmux new -s name` | Create new session |
| `tmux a -t name` | Attach to session |
| `Prefix d` | Detach from session |
| `Prefix s` | List sessions |
| `Prefix $` | Rename session |
| `Prefix (` / `)` | Switch to prev/next session |

## Windows

| Shortcut | Action |
|----------|--------|
| `Prefix c` | Create window |
| `Prefix ,` | Rename window |
| `Prefix &` | Kill window |
| `Prefix Tab` | Next window |
| `Prefix BTab` | Previous window |
| `Prefix 1-9` | Switch to window by number |

## Panes

| Shortcut | Action |
|----------|--------|
| `Prefix` `\|` | Split horizontally |
| `Prefix` `-` | Split vertically |
| `Prefix h/j/k/l` | Move to pane (left/down/up/right) |
| `Prefix H/J/K/L` | Resize pane by 5 (capital = hold-repeat) |
| `Prefix x` | Kill pane |
| `Prefix q` | Show pane numbers |
| `Prefix z` | Toggle pane zoom |
| `Prefix {` / `}` | Swap pane left/right |
| `Prefix space` | Cycle pane layouts |
| `Prefix y` | Toggle synchronize-panes (type in all panes) |

## Copy Mode (vi keys)

| Shortcut | Action |
|----------|--------|
| `Prefix Enter` | Enter copy mode |
| `v` | Begin selection |
| `y` | Copy selection & exit |

Scroll with mouse (mouse mode is on).

## Reload Config

`Prefix r` — reloads `tmux.conf` in-place.

## Plugins (TPM)

- **tmux-yank** — system clipboard integration (select + `y` in copy mode copies to clipboard)
- **catppuccin/tmux** — themed status bar
- **tmux-sensible** — sensible defaults

Install new plugins: add to `.tmux.conf`, then `Prefix I` (capital I) inside tmux.
