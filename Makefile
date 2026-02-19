DIST := dist

# Auto-discover mod directories (those containing a VERSION file)
MODS := $(patsubst %/VERSION,%,$(wildcard */VERSION))
ZIPS := $(foreach m,$(MODS),$(DIST)/$(m)-v$(shell cat $(m)/VERSION).zip)

.PHONY: all clean list

all: $(ZIPS)
	@echo "Built: $(ZIPS)"

# Pattern: dist/<mod>-v<version>.zip ← <mod>/VERSION + all mod files
# Excludes markdown docs, VERSION file, and hidden files from the ZIP.
define MOD_RULE
$(DIST)/$(1)-v$(shell cat $(1)/VERSION).zip: $(shell find $(1) -type f ! -name '*.md' ! -name 'VERSION' ! -path '*/.*')
	@mkdir -p $(DIST)
	@echo "Packing $(1) v$$$$(cat $(1)/VERSION) ..."
	@cd $(1) && zip -r ../$(DIST)/$(1)-v$$$$(cat VERSION).zip . -x '*.md' -x 'VERSION' -x '.*'
endef

$(foreach m,$(MODS),$(eval $(call MOD_RULE,$(m))))

list:
	@$(foreach m,$(MODS),echo "  $(m) v$$(cat $(m)/VERSION)";)

clean:
	rm -rf $(DIST)
