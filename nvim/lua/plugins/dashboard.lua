return {
  {
    "goolord/alpha-nvim",
    event = "VimEnter",
    dependencies = { "nvim-tree/nvim-web-devicons" },
    config = function()
      -- Only show the home screen for plain `nvim`, not `nvim file.py`.
      if vim.fn.argc() > 0 or vim.fn.line2byte('$') ~= -1
          and vim.api.nvim_buf_get_lines(0, 0, -1, false)[1] ~= '' then
        return
      end
      local alpha = require("alpha")
      local dashboard = require("alpha.themes.dashboard")
      dashboard.section.header.val = {
          " ██╗███████╗███╗   ███╗██╗██████╗  █████╗ ██╗     ██████╗  █████╗",
          " ██║╚══███╔╝████╗ ████║██║██╔══██╗██╔══██╗██║     ██╔══██╗██╔══██╗",
          " ██║  ███╔╝ ██╔████╔██║██║██████╔╝███████║██║     ██║  ██║███████║",
          " ██║ ███╔╝  ██║╚██╔╝██║██║██╔══██╗██╔══██║██║     ██║  ██║██╔══██║",
          " ██║███████╗██║ ╚═╝ ██║██║██║  ██║██║  ██║███████╗██████╔╝██║  ██║",
          " ╚═╝╚══════╝╚═╝     ╚═╝╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═════╝ ╚═╝  ╚═╝"
      }
      dashboard.section.buttons.val = {
        dashboard.button("f", "  Find file", ":Telescope find_files<CR>"),
        dashboard.button("n", "  New file", ":ene | startinsert<CR>"),
        dashboard.button("r", "  Recent files", ":Telescope oldfiles<CR>"),
        dashboard.button("g", "  Find text", ":Telescope live_grep<CR>"),
        dashboard.button("e", "  File explorer", ":NvimTreeToggle<CR>"),
        dashboard.button("c", "  Config", ":edit $MYVIMRC<CR>"),
        dashboard.button("l", "  Lazy plugins", ":Lazy<CR>"),
        dashboard.button("q", "  Quit", ":qa<CR>"),
      }
      dashboard.section.footer.val = "✦ IZMIRALDA • Neovim"
      dashboard.section.header.opts.hl = "IzmiraldaLogo"
      dashboard.section.buttons.opts.hl = "IzmiraldaMenu"
      dashboard.section.footer.opts.hl = "IzmiraldaFooter"
      vim.api.nvim_set_hl(0, "IzmiraldaLogo", { fg = "#b8b8b8", bold = true })
      vim.api.nvim_set_hl(0, "IzmiraldaMenu", { fg = "#e0e0e0" })
      vim.api.nvim_set_hl(0, "IzmiraldaFooter", { fg = "#a75c5c", italic = true })
      dashboard.config.layout = {
        { type = "padding", val = 3 },
        dashboard.section.header,
        { type = "padding", val = 2 },
        dashboard.section.buttons,
        { type = "padding", val = 2 },
        dashboard.section.footer,
      }
      alpha.setup(dashboard.config)
    end,
  },
}
