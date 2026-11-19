local M = {}

local signal_handle

local function apply_colors()
  local ok, base16 = pcall(require, "base16-colorscheme")
  if not ok then
    return
  end

  base16.setup({
    base00 = "#000000",
    base01 = "#06101a",
    base02 = "#0a1a2b",
    base03 = "#1d5e8c",
    base04 = "#00a8f4",
    base05 = "#80c8f4",
    base06 = "#80c8f4",
    base07 = "#80c8f4",
    base08 = "#b74e90",
    base09 = "#0ea5e9",
    base0A = "#22d3ee",
    base0B = "#00a8f4",
    base0C = "#87d5f8",
    base0D = "#80d7ff",
    base0E = "#89e7f6",
    base0F = "#41122f",
  })

  local hi = function(group, opts)
    vim.api.nvim_set_hl(0, group, opts)
  end

  hi("TelescopeNormal", { fg = "#80c8f4", bg = "#000000" })
  hi("TelescopeBorder", { fg = "#1d5e8c", bg = "#000000" })
  hi("TelescopePromptNormal", { fg = "#80c8f4", bg = "#000000" })
  hi("TelescopePromptBorder", { fg = "#1d5e8c", bg = "#000000" })
  hi("TelescopePromptPrefix", { fg = "#00a8f4", bg = "#000000" })
  hi("TelescopePromptCounter", { fg = "#00a8f4", bg = "#000000" })
  hi("TelescopePromptTitle", { fg = "#000000", bg = "#00a8f4" })
  hi("TelescopePreviewTitle", { fg = "#000000", bg = "#22d3ee" })
  hi("TelescopeResultsTitle", { fg = "#000000", bg = "#0ea5e9" })
  hi("TelescopeSelection", { fg = "#80c8f4", bg = "#0a1a2b" })
  hi("TelescopeSelectionCaret", { fg = "#00a8f4", bg = "#0a1a2b" })
  hi("TelescopeMatching", { fg = "#00a8f4", bold = true })
end

---Apply the current matugen palette.
function M.setup()
  apply_colors()
end

---Listen for matugen's SIGUSR1 reload signal.
---
---The signal handler reloads this module so that a regenerated palette file is
---picked up. `listen()` is idempotent; registering it from the plugin spec is
---enough, and the handle is kept alive by the callback closure.
function M.listen()
  if signal_handle then
    return
  end

  local uv = vim.uv or vim.loop
  signal_handle = uv.new_signal()
  local handle = signal_handle

  handle:start(
    "sigusr1",
    vim.schedule_wrap(function()
      package.loaded["matugen"] = nil
      local ok, matugen = pcall(require, "matugen")
      if ok and matugen.setup then
        pcall(matugen.setup)
      end
    end)
  )
end

return M
