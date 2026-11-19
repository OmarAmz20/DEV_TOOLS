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

-- Make tools installed with uv/pipx available to Neovim (e.g. flake8),
-- even when Neovim is launched from the desktop instead of a shell.
local user_bin = vim.fn.expand("~/.local/bin")
if vim.fn.isdirectory(user_bin) == 1 and not (vim.env.PATH or ""):find(user_bin, 1, true) then
  vim.env.PATH = user_bin .. ":" .. (vim.env.PATH or "")
end

-- Basic options
vim.opt.number = true
vim.opt.relativenumber = true
vim.opt.expandtab = true
vim.opt.shiftwidth = 2
vim.opt.tabstop = 2
vim.opt.termguicolors = true
vim.g.mapleader = " "
vim.opt.clipboard:append("unnamedplus")

-- This config is pure Lua; the optional remote-plugin providers are unused.
vim.g.loaded_python3_provider = 0
vim.g.loaded_node_provider = 0
vim.g.loaded_perl_provider = 0
vim.g.loaded_ruby_provider = 0

require("lazy").setup({
  { import = "plugins" },

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
      vim.keymap.set("n", "<leader>e", "<cmd>NvimTreeToggle<CR>", { desc = "Toggle file explorer" })
    end,
  },

  -- Finder
  {
    "nvim-telescope/telescope.nvim",
    dependencies = { "nvim-lua/plenary.nvim" },
    config = function()
      local builtin = require("telescope.builtin")
      vim.keymap.set("n", "<leader>ff", builtin.find_files, { desc = "Find files" })
      vim.keymap.set("n", "<leader>fg", builtin.live_grep, { desc = "Live grep" })
      vim.keymap.set("n", "<leader>fb", builtin.buffers, { desc = "Buffers" })
      vim.keymap.set("n", "<leader>fh", builtin.help_tags, { desc = "Help tags" })
      vim.keymap.set("n", "<leader>t", function()
        vim.cmd("botright vsplit | term")
      end, { desc = "Open terminal" })
    end,
  },

  -- Markdown inline rendering
  {
    "MeanderingProgrammer/render-markdown.nvim",
    dependencies = {
      "nvim-treesitter/nvim-treesitter",
      "nvim-tree/nvim-web-devicons",
    },
    opts = {
      -- No LaTeX tooling installed, so skip math rendering.
      latex = { enabled = false },
    },
    name = "render-markdown",
  },

  -- Treesitter (main branch, required for Neovim 0.12+)
  {
    "nvim-treesitter/nvim-treesitter",
    branch = "main",
    lazy = false,
    build = ":TSUpdate",
    config = function()
      local ts = require("nvim-treesitter")
      ts.setup()
      ts.install({
        "markdown",
        "markdown_inline",
        "html",
        "yaml",
        "lua",
        "python",
        "json",
        "make",
        "gitignore",
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
      local sources = {}

      -- Only register flake8 when it is actually installed, otherwise
      -- none-ls logs a warning on every run.
      if vim.fn.executable("flake8") == 1 then
        sources[#sources + 1] = require("none-ls.diagnostics.flake8")
      end

      null_ls.setup({ sources = sources })
    end,
  },
}, {
  -- No plugin needs luarocks; don't report it as a health error.
  rocks = { enabled = false },
})

-- nvim-treesitter's main branch does not enable highlighting automatically.
vim.api.nvim_create_autocmd("FileType", {
  callback = function(args)
    pcall(vim.treesitter.start, args.buf)
  end,
  desc = "Enable Tree-sitter highlighting",
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
local pdf_viewer
for _, candidate in ipairs({ "zathura", "xdg-open" }) do
  if vim.fn.executable(candidate) == 1 then
    pdf_viewer = candidate
    break
  end
end

vim.api.nvim_create_autocmd("BufReadCmd", {
  pattern = { "*.pdf" },
  callback = function()
    local path = vim.fn.expand("%:p")
    if not pdf_viewer then
      vim.notify("No PDF viewer found (install zathura or xdg-open)", vim.log.levels.WARN)
    elseif vim.fn.jobstart({ pdf_viewer, path }, { detach = true }) <= 0 then
      vim.notify(("Failed to launch %s for %s"):format(pdf_viewer, path), vim.log.levels.WARN)
    end
    vim.cmd("bwipeout!")
  end,
})
