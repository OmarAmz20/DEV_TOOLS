return {
  "RRethy/base16-nvim",
  config = function()
    -- Keep matugen's SIGUSR1 listener available, but do not apply the palette
    -- at startup: the blackmetal colorscheme is the default theme.
    local ok, matugen = pcall(require, "matugen")
    if ok then
      matugen.listen()
    end
  end,
}
