{
  description = "MediaTamer (organize + extract MKV metadata)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs =
    { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
    in
    {

      packages."${system}".default = pkgs.python3Packages.buildPythonPackage rec {
        pname = "mediatamer";
        version = "0.1.0";
        src = ./.;
        nativeBuildInputs = [
          pkgs.python3
          pkgs.python3Packages.setuptools
          pkgs.python3Packages.wheel
        ];
        nativeCheckInputs = [
          pkgs.python3Packages.pytestCheckHook
        ];
        propagatedBuildInputs = [
          pkgs.ffmpeg
          pkgs.mkvtoolnix
          pkgs.mediainfo
          pkgs.handbrake
          pkgs.tesseract
          pkgs.python3Packages.argcomplete
          pkgs.python3Packages.requests
          pkgs.python3Packages.pytesseract
          pkgs.python3Packages.pillow
          pkgs.python3Packages.langdetect
          pkgs.python3Packages.pyyaml
        ];
        pyproject = true;
        meta = with pkgs.lib; {
          description = "MediaTamer — organize media and extract MKV metadata";
          license = licenses.mit;
        };
        # doCheck = true;
        doCheck = false;
        pythonImportsCheck = [ "mediatamer" ];
      };

      devShells."${system}".default = pkgs.mkShell {
        name = "mediatamer-dev";
        packages = [
          self.packages."${system}".default
        ];
        shellHook = ''
          export SUBTITLE_CACHE_DIR="/data/videos/unsorted_video_subtitle_cache"
          eval "$(register-python-argcomplete mediatamer)"
        '';
      };

      defaultPackage = self.packages."${system}".default;
    };
}
