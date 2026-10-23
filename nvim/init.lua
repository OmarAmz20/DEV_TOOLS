-- ~/.config/nvim/init.lua

-- Bootstrap lazy.nvim
local lazypath = vim.fn.stdpath("data") .. "/lazy/lazy.nvim"
if not (vim.uv or vim.loop).fs_stat(lazypath) then
  vim.fn.system({
    "git", "clone", "--filter=blob:none",
    "https://github.com/folke/lazy.nvim.git",
    "--branch=stable", lazypath,
  })
end
vim.opt.rtp:prepend(lazypath)

-- Basic options
vim.opt.number = true
vim.opt.relativenumber = true
vim.opt.expandtab = true
vim.opt.shiftwidth = 2
vim.opt.tabstop = 2
vim.opt.termguicolors = true
vim.g.mapleader = " "
vim.opt.clipboard:append("unnamedplus")

require("lazy").setup({
  -- Suggestions on demand (no automatic completion)
  {
    "hrsh7th/nvim-cmp",
    dependencies = {
      "hrsh7th/cmp-buffer",
      "hrsh7th/cmp-path",
    },
    config = function()
      local cmp = require("cmp")

      vim.opt.completeopt = { "menu", "menuone", "noselect" }

      cmp.setup({
        completion = {
          autocomplete = false,
        },
        sources = {
          { name = "buffer", keyword_length = 2 },
          { name = "path" },
        },
        mapping = cmp.mapping.preset.insert({
          ["<C-Space>"] = cmp.mapping.complete(),
          ["<C-n>"] = cmp.mapping.select_next_item(),
          ["<C-p>"] = cmp.mapping.select_prev_item(),
          ["<CR>"] = cmp.mapping.confirm({ select = false }),
          ["<C-e>"] = cmp.mapping.abort(),
        }),
      })
    end,
  },

  -- Explorer
  {
    "nvim-tree/nvim-tree.lua",
    dependencies = { "nvim-tree/nvim-web-devicons" },
    config = function()
      require("nvim-tree").setup({})
      vim.keymap.set("n", "<leader>e", ":NvimTreeToggle<CR>")
    end,
  },

  -- Finder
  {
    "nvim-telescope/telescope.nvim",
    dependencies = { "nvim-lua/plenary.nvim" },
    config = function()
      local builtin = require("telescope.builtin")
      vim.keymap.set("n", "<leader>ff", builtin.find_files, {})
      vim.keymap.set("n", "<leader>fg", builtin.live_grep, {})
      vim.keymap.set("n", "<leader>fb", builtin.buffers, {})
      vim.keymap.set("n", "<leader>t", function()
        vim.cmd("botright vsplit | term")
      end, {})
    end,
  },

  -- Markdown inline rendering
  {
    "MeanderingProgrammer/render-markdown.nvim",
    dependencies = {
      "nvim-treesitter/nvim-treesitter",
      "nvim-tree/nvim-web-devicons",
    },
    opts = {},
    name = "render-markdown",
  },

  -- Treesitter
  {
    "nvim-treesitter/nvim-treesitter",
    branch = "master",
    build = ":TSUpdate",
    config = function()
      require("nvim-treesitter.configs").setup({
        ensure_installed = { "markdown", "markdown_inline" },
        auto_install = true,
        highlight = { enable = true },
      })
    end,
  },

  -- Flake8 diagnostics (via none-ls)
  {
    "nvimtools/none-ls.nvim",
    dependencies = {
      "nvim-lua/plenary.nvim",
      "nvimtools/none-ls-extras.nvim",
    },
    config = function()
      local null_ls = require("null-ls")
      null_ls.setup({
        sources = {
          require("none-ls.diagnostics.flake8"),
        },
      })
    end,
  },
})

-- Black metal theme: pure black, bone white, dusty red.
pcall(vim.cmd.colorscheme, "blackmetal")

-- Keep file icons monochrome.
local ok_devicons, devicons = pcall(require, "nvim-web-devicons")
if ok_devicons then
  local normal = vim.api.nvim_get_hl(0, { name = "Normal" })
  if normal.fg then
    local fg = string.format("#%06x", normal.fg)
    devicons.setup({
      color_icons = false,
      override = {
        default_icon = { icon = "", color = fg, name = "Default" },
      },
    })
    for name in pairs(vim.api.nvim_get_hl(0, {})) do
      if name:match("^DevIcon") then
        vim.api.nvim_set_hl(0, name, { fg = normal.fg, bg = normal.bg })
      end
    end
  end
end

-- Open PDFs with zathura (xdg-open fallback)
local pdf_viewer = vim.fn.executable("zathura") == 1 and "zathura" or "xdg-open"
vim.api.nvim_create_autocmd("BufReadCmd", {
  pattern = { "*.pdf" },
  callback = function()
    vim.fn.jobstart({ pdf_viewer, vim.fn.expand("%:p") }, { detach = true })
    vim.cmd("bw")
  end,
})
