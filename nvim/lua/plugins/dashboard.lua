return {
  {
    "goolord/alpha-nvim",
    dependencies = { "nvim-tree/nvim-web-devicons" },
    config = function()
      -- Only show the home screen for plain `nvim`, not `nvim file.py`.
      if vim.fn.argc() > 0 then
        return
      end

      local buf = vim.api.nvim_get_current_buf()
      local first_line = vim.api.nvim_buf_get_lines(buf, 0, 1, false)[1] or ""
      if vim.api.nvim_buf_get_name(buf) ~= "" or first_line ~= "" then
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

      -- Re-apply on every colorscheme change, otherwise loading a theme after
      -- this config wipes these groups.
      local function set_dashboard_highlights()
        vim.api.nvim_set_hl(0, "IzmiraldaLogo", { fg = "#b8b8b8", bold = true })
        vim.api.nvim_set_hl(0, "IzmiraldaMenu", { fg = "#e0e0e0" })
        vim.api.nvim_set_hl(0, "IzmiraldaFooter", { fg = "#a75c5c", italic = true })
      end

      set_dashboard_highlights()
      vim.api.nvim_create_autocmd("ColorScheme", {
        callback = set_dashboard_highlights,
        desc = "Restore dashboard highlights",
      })
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
