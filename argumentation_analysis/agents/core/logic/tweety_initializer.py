import jpype
import jpype.imports
from jpype.types import JString
import logging
from argumentation_analysis.utils.core_utils.logging_utils import setup_logging
# from argumentation_analysis.utils.core_utils.path_operations import get_project_root # Différé
from pathlib import Path
import os # Ajout de l'import os
import subprocess # Ajout pour exécuter des commandes shell

# Initialisation du logger pour ce module.
# setup_logging() est appelé pour configurer le logging global.
# Il est important que setup_logging soit idempotent ou gère les appels multiples (ce qu'il fait avec force=True).
setup_logging("INFO")  # Appel avec un niveau de log valide comme "INFO" ou selon la config souhaitée.
logger = logging.getLogger(__name__) # Obtention correcte du logger pour ce module.

class TweetyInitializer:
    """
    Handles the initialization of JVM components for TweetyProject.
    This includes starting the JVM, setting up classpaths, and initializing
    specific logic components like PL, FOL, and Modal logic.
    """

    _jvm_started = False
    _pl_reasoner = None
    _pl_parser = None
    _fol_parser = None
    _fol_reasoner = None
    _modal_logic = None
    _modal_parser = None
    _modal_reasoner = None
    _tweety_bridge = None # Reference to the main bridge

    def __init__(self, tweety_bridge_instance):
        self._tweety_bridge = tweety_bridge_instance
        if not TweetyInitializer._jvm_started:
            self._start_jvm()

    def _start_jvm(self):
        """Starts the JVM and sets up the classpath."""
        global logger # Assurer qu'on référence le logger du module
        # Le logger devrait maintenant être initialisé correctement au niveau du module.
        # Ce bloc if logger is None peut rester comme une double sécurité, mais ne devrait idéalement pas être atteint.
        if logger is None:
            # Cela ne devrait plus se produire si l'initialisation au niveau du module est correcte.
            setup_logging("INFO")
            logger = logging.getLogger(__name__)
            logger.error("CRITICAL: TweetyInitializer module logger was None and had to be re-initialized in _start_jvm. This indicates an issue in module loading or initial logger setup.")

        if TweetyInitializer._jvm_started:
            logger.info("JVM already started.")
            return

        try:
            # Importation dynamique de get_project_root UNIQUEMENT si on doit démarrer la JVM
            from argumentation_analysis.utils.system_utils import get_project_root # Chemin corrigé
            project_root = get_project_root()
            tweety_lib_path = project_root / "libs" / "tweety"
            
            # Log des contenus des répertoires pour le débogage
            logger.info(f"Contenu de tweety_lib_path ({tweety_lib_path}):")
            try:
                for item in os.listdir(tweety_lib_path):
                    logger.info(f"  - {item}")
            except Exception as e_ls:
                logger.error(f"    Impossible de lister {tweety_lib_path}: {e_ls}")

            tweety_actual_lib_dir = tweety_lib_path / "lib"
            logger.info(f"Contenu de tweety_actual_lib_dir ({tweety_actual_lib_dir}):")
            try:
                if tweety_actual_lib_dir.exists() and tweety_actual_lib_dir.is_dir():
                    for item in os.listdir(tweety_actual_lib_dir):
                        logger.info(f"  - {item}")
                else:
                    logger.info(f"    Le répertoire {tweety_actual_lib_dir} n'existe pas ou n'est pas un répertoire.")
            except Exception as e_ls_lib:
                logger.error(f"    Impossible de lister {tweety_actual_lib_dir}: {e_ls_lib}")

            tweety_jar_file = tweety_lib_path / "org.tweetyproject.tweety-full-1.28-with-dependencies.jar"
            logger.info(f"Inspection du contenu de {tweety_jar_file}:")
            if tweety_jar_file.exists():
                try:
                    # S'assurer que JAVA_HOME est défini et que jar est dans le PATH ou utiliser le chemin complet vers jar
                    java_home = os.getenv("JAVA_HOME")
                    if java_home:
                        jar_executable = Path(java_home) / "bin" / "jar"
                        if not jar_executable.exists(): # Essayer sans .exe pour Linux/macOS
                             jar_executable = Path(java_home) / "bin" / "jar" # Redondant, mais pour être explicite
                    else: # Si JAVA_HOME n'est pas défini, on espère que 'jar' est dans le PATH
                        jar_executable = "jar"
                    
                    logger.info(f"Utilisation de l'exécutable jar: {jar_executable}")
                    result = subprocess.run([str(jar_executable), "tf", str(tweety_jar_file)], capture_output=True, text=True, check=False)
                    if result.returncode == 0:
                        logger.info(f"Contenu de {tweety_jar_file} (premières lignes):\n{os.linesep.join(result.stdout.splitlines()[:20])}")
                        if "org/tweetyproject/" not in result.stdout:
                            logger.warning(f"Le package 'org/tweetyproject/' ne semble PAS être à la racine de {tweety_jar_file}!")
                        else:
                            logger.info(f"Le package 'org/tweetyproject/' semble être présent dans {tweety_jar_file}.")
                    else:
                        logger.error(f"Erreur lors de l'inspection de {tweety_jar_file} avec jar tf: {result.stderr}")
                except FileNotFoundError:
                    logger.error(f"La commande 'jar' n'a pas été trouvée. Assurez-vous que le JDK est installé et que 'jar' est dans le PATH ou que JAVA_HOME est correctement défini.")
                except Exception as e_jar:
                    logger.error(f"Exception lors de l'inspection de {tweety_jar_file}: {e_jar}")
            else:
                logger.error(f"Le fichier {tweety_jar_file} n'existe pas.")

            # Updated classpath based on previous successful runs
            classpath_entries = [
                tweety_jar_file, # Utilisation de la variable déjà définie
                # tweety_actual_lib_dir / "*", # General libs - Répertoire vide, donc inutile pour l'instant
            ]
            
            # Convert Path objects to strings for jpype
            classpath = [str(p) for p in classpath_entries]
            logger.info(f"Calculated Classpath: {classpath}")

            if not jpype.isJVMStarted():
                logger.info("Starting JVM...")
                jpype.startJVM(
                    jpype.getDefaultJVMPath(),
                    "-ea",
                    f"-Djava.class.path={os.pathsep.join(classpath)}", # Utilisation de os.pathsep
                    convertStrings=False
                )
                TweetyInitializer._jvm_started = True
                logger.info("JVM started successfully.")
            else:
                logger.info("JVM was already started by another component.")
                TweetyInitializer._jvm_started = True

            # Log the actual classpath from Java System properties
            java_system = jpype.JClass("java.lang.System")
            actual_classpath = java_system.getProperty("java.class.path")
            logger.info(f"Actual Java Classpath from System.getProperty: {actual_classpath}")

            # Import necessary Java classes after JVM start
            self._import_java_classes()

        except Exception as e:
            logger.error(f"Failed to start or connect to JVM: {e}", exc_info=True)
            # Propagate the exception if critical for the application
            raise RuntimeError(f"JVM Initialization failed: {e}") from e

    def _import_java_classes(self):
        """Imports Java classes required by TweetyBridge."""
        
        # --- DEBUT BLOC DE DIAGNOSTIC ArrayList ---
        if not TweetyInitializer._jvm_started:
            logger.error("JVM not started prior to _import_java_classes. Cannot import Java classes for ArrayList test.")
            # Ne pas lever d'erreur ici pour laisser la suite échouer si c'est le cas,
            # bien que _start_jvm devrait déjà avoir levé une erreur si la JVM n'a pas démarré.
        else:
            try:
                logger.info("DIAGNOSTIC: Attempting to load java.util.ArrayList...")
                _ = jpype.JClass("java.util.ArrayList") # Test load
                logger.info("DIAGNOSTIC: Successfully loaded java.util.ArrayList.")
            except Exception as e_arraylist:
                logger.error(f"DIAGNOSTIC: Failed to load java.util.ArrayList: {e_arraylist}", exc_info=True)
                # Ne pas lever d'erreur ici, pour voir si les classes Tweety échouent ensuite
        # --- FIN BLOC DE DIAGNOSTIC ArrayList ---

        logger.info("Attempting to import TweetyProject Java classes...")
        try:
            # Propositional Logic
            # jpype.imports.org.tweetyproject.logics.pl.syntax # Old way
            _ = jpype.JClass("org.tweetyproject.logics.pl.syntax.PlSignature")
            _ = jpype.JClass("org.tweetyproject.logics.pl.syntax.Proposition")
            _ = jpype.JClass("org.tweetyproject.logics.pl.syntax.PlBeliefSet")
            # jpype.imports.org.tweetyproject.logics.pl.reasoner # Old way
            _ = jpype.JClass("org.tweetyproject.logics.pl.reasoner.SatReasoner")
            # jpype.imports.org.tweetyproject.logics.pl.sat # Old way
            _ = jpype.JClass("org.tweetyproject.logics.pl.sat.Sat4jSolver")
            
            # First-Order Logic
            # jpype.imports.org.tweetyproject.logics.fol.syntax # Old way
            _ = jpype.JClass("org.tweetyproject.logics.fol.syntax.FolSignature")
            _ = jpype.JClass("org.tweetyproject.logics.fol.syntax.FolBeliefSet")
            # jpype.imports.org.tweetyproject.logics.fol.reasoner # Old way
            _ = jpype.JClass("org.tweetyproject.logics.fol.reasoner.SimpleFolReasoner")
            
            # Modal Logic
            # jpype.imports.org.tweetyproject.logics.ml.syntax # Old way
            _ = jpype.JClass("org.tweetyproject.logics.ml.syntax.MlFormula") # Attempting to use MlFormula for ModalLogic types
            _ = jpype.JClass("org.tweetyproject.logics.ml.syntax.MlBeliefSet")
            # jpype.imports.org.tweetyproject.logics.ml.reasoner # Old way
            _ = jpype.JClass("org.tweetyproject.logics.ml.reasoner.SimpleMlReasoner") # KrHyperModalReasoner non trouvé dans le JAR
            # jpype.imports.org.tweetyproject.logics.ml.parser.MlParser # Old way
            _ = jpype.JClass("org.tweetyproject.logics.ml.parser.MlParser")
            
            # General TweetyProject classes
            _ = jpype.JClass("org.tweetyproject.commons.ParserException")
            _ = jpype.JClass("org.tweetyproject.logics.commons.syntax.Sort")
            logger.info("Successfully imported TweetyProject Java classes.")
        except Exception as e:
            logger.error(f"Error importing Java classes: {e}", exc_info=True)
            raise RuntimeError(f"Java class import failed: {e}") from e


    def initialize_pl_components(self):
        """Initializes components for Propositional Logic."""
        if not TweetyInitializer._jvm_started:
            self._start_jvm()
        try:
            logger.debug("Initializing PL components...")
            TweetyInitializer._pl_reasoner = jpype.JClass("org.tweetyproject.logics.pl.reasoner.SatReasoner")()
            TweetyInitializer._pl_parser = jpype.JClass("org.tweetyproject.logics.pl.parser.PlParser")()
            logger.info("PL components initialized.")
            return TweetyInitializer._pl_parser, TweetyInitializer._pl_reasoner
        except Exception as e:
            logger.error(f"Error initializing PL components: {e}", exc_info=True)
            raise

    def initialize_fol_components(self):
        """Initializes components for First-Order Logic."""
        if not TweetyInitializer._jvm_started:
            self._start_jvm()
        try:
            logger.debug("Initializing FOL components...")
            TweetyInitializer._fol_parser = jpype.JClass("org.tweetyproject.logics.fol.parser.FolParser")()
            # FOL reasoner might depend on specific setup or be a more general interface
            # For now, let's assume a default or no specific reasoner instance needed at class level
            # TweetyInitializer._fol_reasoner = ...
            logger.info("FOL parser initialized.")
            return TweetyInitializer._fol_parser
        except Exception as e:
            logger.error(f"Error initializing FOL components: {e}", exc_info=True)
            raise

    def initialize_modal_components(self):
        """Initializes components for Modal Logic."""
        if not TweetyInitializer._jvm_started:
            self._start_jvm()
        try:
            logger.debug("Initializing Modal Logic components...")
            # Modal logic might have different types (K, S4, S5 etc.)
            # For now, let's assume a general parser and perhaps a default logic
            # The MlParser class was specifically imported
            TweetyInitializer._modal_parser = jpype.JClass("org.tweetyproject.logics.ml.parser.MlParser")()
            
            # Example: Defaulting to S4 logic if a specific one is needed for the reasoner
            # TweetyLogic = jpype.JClass("org.tweetyproject.logics.ml.syntax.ModalLogicType")
            # TweetyInitializer._modal_logic = TweetyLogic.S4

            # Modal reasoner might also depend on the specific modal logic type
            # TweetyInitializer._modal_reasoner = ...
            logger.info("Modal Logic parser initialized.")
            return TweetyInitializer._modal_parser
        except Exception as e:
            logger.error(f"Error initializing Modal Logic components: {e}", exc_info=True)
            raise

    @staticmethod
    def get_pl_parser():
        if TweetyInitializer._pl_parser is None:
            # This might indicate an issue if called before initialization by the bridge
            logger.warning("PL Parser accessed before explicit initialization by TweetyBridge.")
            # Fallback or error, for now, let's assume bridge handles init order
        return TweetyInitializer._pl_parser

    @staticmethod
    def get_pl_reasoner():
        return TweetyInitializer._pl_reasoner

    @staticmethod
    def get_fol_parser():
        return TweetyInitializer._fol_parser
    
    @staticmethod
    def get_modal_parser():
        return TweetyInitializer._modal_parser

    # Add other static getters if needed for reasoners or specific logic instances

    def is_jvm_started(self):
        """Checks if the JVM is started."""
        return TweetyInitializer._jvm_started

    def shutdown_jvm(self):
        """Shuts down the JVM if it was started by this class."""
        if TweetyInitializer._jvm_started and jpype.isJVMStarted():
            try:
                # Perform any necessary cleanup of TweetyProject resources here
                # For example, explicitly nullifying static references if they hold onto Java objects
                TweetyInitializer._pl_reasoner = None
                TweetyInitializer._pl_parser = None
                TweetyInitializer._fol_parser = None
                TweetyInitializer._fol_reasoner = None
                TweetyInitializer._modal_logic = None
                TweetyInitializer._modal_parser = None
                TweetyInitializer._modal_reasoner = None
                
                logger.info("Shutting down JVM...")
                jpype.shutdownJVM()
                TweetyInitializer._jvm_started = False
                logger.info("JVM shut down successfully.")
            except Exception as e:
                logger.error(f"Error during JVM shutdown: {e}", exc_info=True)
        elif not TweetyInitializer._jvm_started:
            logger.info("JVM was not started by this class or already shut down.")
        else:
            logger.info("JVM is started but perhaps not by this class, not shutting down.")